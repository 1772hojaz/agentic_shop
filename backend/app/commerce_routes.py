"""Versioned catalogue, cart, inventory, order and payment interfaces."""

from decimal import Decimal
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select

from app.auth import current_principal, require
from app.catalogue import (
    cart_detail,
    create_product,
    get_record,
    page,
    product_detail,
    search_products,
    serialize,
    set_cart,
    update_product,
)
from app.config import get_settings
from app.database import audit, get_db, new_id
from app.models import (
    Category,
    Inventory,
    Order,
    Payment,
    Product,
    StockMovement,
    Variant,
)
from app.orders import checkout, order_detail, visible_order
from app.payments import initiate_payment
from app.registry import execute_tool
from app.schemas import (
    CartInput,
    CategoryInput,
    Checkout,
    OrderStatus,
    PaymentInput,
    PriceInput,
    ProductInput,
    ProductUpdate,
    Search,
    StockInput,
    ThresholdInput,
    VariantInput,
)

router = APIRouter(prefix="/api/v1", tags=["Commerce"])


@router.patch("/inventory/{variant_id}/threshold")
def stock_threshold(
    variant_id: str,
    data: ThresholdInput,
    actor=Depends(require("inventory.write")),
    db=Depends(get_db),
):
    """Request an exact low-stock threshold change."""
    if variant_id != data.variant_id:
        raise HTTPException(422, "Variant mismatch")
    return execute_tool(db, actor, "stock_threshold", data.model_dump())


@router.post("/products/{product_id}/variants", status_code=201)
def add_variant(
    product_id: str,
    data: VariantInput,
    actor=Depends(require("products.write")),
    db=Depends(get_db),
):
    """Add a separately priced and stocked product option."""
    if data.quantity:
        actor.require("inventory.write")
    get_record(db, Product, product_id)
    variant = Variant(
        product_id=product_id,
        **data.model_dump(exclude={"quantity", "low_stock_threshold"}),
    )
    db.add(variant)
    db.flush()
    db.add(
        Inventory(
            variant_id=variant.id,
            quantity=data.quantity,
            low_stock_threshold=data.low_stock_threshold,
        )
    )
    db.add(
        StockMovement(
            variant_id=variant.id,
            delta=data.quantity,
            reason="Opening balance",
            actor_id=actor.id,
        )
    )
    audit(db, actor.id, "variant.create", variant.id)
    return serialize(variant)


@router.patch("/categories/{category_id}")
def edit_category(
    category_id: str,
    data: CategoryInput,
    actor=Depends(require("products.write")),
    db=Depends(get_db),
):
    """Rename an existing category without changing product references."""
    record = get_record(db, Category, category_id)
    record.name = data.name
    audit(db, actor.id, "category.update", record.id)
    return serialize(record)


@router.get("/products")
def products(
    query: str = Query("", max_length=160),
    category_id: str | None = None,
    max_price: Decimal | None = Query(None, ge=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    db=Depends(get_db),
):
    """Browse the public catalogue with bounded pagination."""
    criteria = Search(
        query=query, category_id=category_id, max_price=max_price
    )
    return search_products(db, criteria, offset, limit)


@router.get("/products/{product_id}")
def product(product_id: str, db=Depends(get_db)):
    """Retrieve a live product and its available variants."""
    record = get_record(db, Product, product_id)
    if not record.active:
        raise HTTPException(404, "Product not found")
    return product_detail(db, record)


@router.post("/products", status_code=201)
def add_product(
    data: ProductInput,
    actor=Depends(require("products.write")),
    db=Depends(get_db),
):
    """Create a product and its opening inventory."""
    return create_product(db, actor, data)


@router.patch("/products/{product_id}")
def edit_product(
    product_id: str,
    data: ProductUpdate,
    actor=Depends(require("products.write")),
    db=Depends(get_db),
):
    """Edit catalogue information without silently changing prices."""
    return update_product(db, actor, product_id, data)


@router.delete("/products/{product_id}")
def archive_product(
    product_id: str,
    actor=Depends(require("products.write")),
    db=Depends(get_db),
):
    """Archive catalogue records while preserving historical references."""
    record = get_record(db, Product, product_id)
    record.active = False
    audit(db, actor.id, "product.archive", record.id)
    return {"archived": True}


@router.post("/variants/{variant_id}/price")
def change_price(
    variant_id: str,
    data: PriceInput,
    actor=Depends(require("products.write")),
    db=Depends(get_db),
):
    """Request a price change and return an exact confirmation payload."""
    if variant_id != data.variant_id:
        raise HTTPException(422, "Variant mismatch")
    return execute_tool(db, actor, "product_price", data.model_dump())


@router.post("/uploads", status_code=201)
def upload_image(
    file: UploadFile = File(...),
    actor=Depends(require("products.write")),
):
    """Decode and re-encode bounded images instead of trusting file names."""
    from io import BytesIO

    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Image must be smaller than 5 MB")
    try:
        image = Image.open(BytesIO(content))
        if image.width * image.height > 16000000:
            raise HTTPException(413, "Image dimensions exceed the limit")
        image = image.convert("RGB")
        image.thumbnail((1600, 1600))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "Invalid image") from None
    folder = Path(get_settings().upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    name = new_id() + ".jpg"
    image.save(folder / name, "JPEG", quality=85)
    return {"url": "/uploads/" + name}


@router.get("/categories")
def categories(db=Depends(get_db)):
    """List catalogue category names."""
    return {"items": [serialize(row) for row in db.scalars(select(Category))]}


@router.post("/categories", status_code=201)
def add_category(
    data: CategoryInput,
    actor=Depends(require("products.write")),
    db=Depends(get_db),
):
    """Create a category for product assignment."""
    category = Category(name=data.name)
    db.add(category)
    db.flush()
    audit(db, actor.id, "category.create", category.id)
    return serialize(category)


