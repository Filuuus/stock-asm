from .models import ProductImage, ProductPriceVisibility


def get_images_by_codes(codes):
    images = ProductImage.objects.filter(producto_codigo__in=codes).order_by("producto_codigo", "order")
    by_code = {}
    for img in images:
        by_code.setdefault(img.producto_codigo, []).append(
            {"file": img.file, "is_primary": img.is_primary}
        )
    return by_code


def get_public_price_codes():
    return set(ProductPriceVisibility.objects.filter(public=True).values_list("producto_codigo", flat=True))
