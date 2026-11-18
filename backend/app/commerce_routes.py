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


@router.get("/inventory/movements")
def movements(
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor=Depends(require("inventory.read")),
    db=Depends(get_db),
):
    """Retrieve stock adjustment history with reasons and actors."""
    return page(
        db,
        select(StockMovement).order_by(StockMovement.created_at.desc()),
        offset,
        limit,
    )


@router.get("/inventory")
def inventory(
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor=Depends(require("inventory.read")),
    db=Depends(get_db),
):
    """List stock balances with readable product and option labels."""
    result = page(
        db, select(Inventory).order_by(Inventory.quantity), offset, limit
    )
    for row in result["items"]:
        variant = get_record(db, Variant, row["variant_id"])
        row["sku"] = variant.sku
        row["price"] = variant.price
        row["options"] = variant.options
        row["name"] = get_record(db, Product, variant.product_id).name
    return result


@router.patch("/inventory/{variant_id}")
def adjust_stock(
    variant_id: str,
    data: StockInput,
    actor=Depends(require("inventory.write")),
    db=Depends(get_db),
):
    """Request a stock adjustment requiring explicit human confirmation."""
    if variant_id != data.variant_id:
        raise HTTPException(422, "Variant mismatch")
    return execute_tool(db, actor, "stock_adjustment", data.model_dump())


@router.get("/carts/me")
def view_cart(actor=Depends(current_principal), db=Depends(get_db)):
    """Retrieve only the authenticated customer's cart."""
    return cart_detail(db, actor)


@router.put("/carts/me/items")
def cart_item(
    data: CartInput, actor=Depends(current_principal), db=Depends(get_db)
):
    """Set a quantity in the current customer's personal cart."""
    return set_cart(db, actor, data)


@router.post("/orders", status_code=201)
def create_order(
    data: Checkout, actor=Depends(current_principal), db=Depends(get_db)
):
    """Reserve a cart and create an unpaid order."""
    return checkout(db, actor, data)


@router.get("/orders")
def orders(
    status: str = "",
    query: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor=Depends(current_principal),
    db=Depends(get_db),
):
    """List authorised orders, applying ownership before filtering."""
    statement = select(Order).order_by(Order.created_at.desc())
    if actor.context == "customer":
        statement = statement.where(Order.customer_id == actor.id)
    else:
        actor.require("orders.read")
    if status:
        statement = statement.where(Order.status == status)
    if query:
        statement = statement.where(Order.id.contains(query))
    return page(db, statement, offset, limit)


@router.get("/orders/{order_id}")
def view_order(
    order_id: str, actor=Depends(current_principal), db=Depends(get_db)
):
    """Retrieve order details only after ownership or staff permission."""
    return order_detail(db, visible_order(db, actor, order_id))


@router.patch("/orders/{order_id}/status")
def order_status(
    order_id: str,
    data: OrderStatus,
    actor=Depends(require("orders.write")),
    db=Depends(get_db),
):
    """Request an order state transition requiring human confirmation."""
    if order_id != data.order_id:
        raise HTTPException(422, "Order mismatch")
    return execute_tool(db, actor, "order_management", data.model_dump())


@router.post("/payments/initiate")
def start_payment(
    data: PaymentInput, actor=Depends(current_principal), db=Depends(get_db)
):
    """Initiate cash instructions or real hosted Stripe checkout."""
    return initiate_payment(db, actor, data)


@router.get("/payments/{payment_id}")
def get_payment(
    payment_id: str, actor=Depends(current_principal), db=Depends(get_db)
):
    """Read payment status after authorising its parent order."""
    record = get_record(db, Payment, payment_id)
    visible_order(db, actor, record.order_id)
    return serialize(record)
