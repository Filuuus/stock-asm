from .models import ProductImage


def get_images_by_codes(codes):
    images = ProductImage.objects.filter(producto_codigo__in=codes).order_by("producto_codigo", "order")
    by_code = {}
    for img in images:
        by_code.setdefault(img.producto_codigo, []).append(
            {"file": img.file, "is_primary": img.is_primary}
        )
    return by_code
