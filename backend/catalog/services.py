import os
import secrets

from django.conf import settings
from django.core.cache import cache
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import ProductImage

PRODUCTS_DIR = settings.BASE_DIR.parent / 'frontend' / 'public' / 'products'
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_SIDE = 1200


def get_images_by_codes(codes):
    images = ProductImage.objects.filter(producto_codigo__in=codes).order_by("producto_codigo", "order")
    by_code = {}
    for img in images:
        by_code.setdefault(img.producto_codigo, []).append(
            {"id": img.pk, "file": img.file, "is_primary": img.is_primary}
        )
    return by_code


class PhotoError(ValueError):
    """Shown to the user."""


def save_photo(code, upload):
    """A staff photo (usually straight from a phone camera): upright, at most
    MAX_SIDE, padded to a white square like the rest, saved as webp under a
    random name (names never carry the part number)."""
    if upload.size > MAX_UPLOAD_BYTES:
        raise PhotoError('La foto pesa más de 20 MB.')
    try:
        im = ImageOps.exif_transpose(Image.open(upload)).convert('RGBA')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise PhotoError('El archivo no es una imagen.')
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    side = max(im.size)
    # Transparent backgrounds (manufacturer PNGs) end up white, not black.
    square = Image.new('RGB', (side, side), 'white')
    square.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
    name = secrets.token_hex(8) + '.webp'
    square.save(PRODUCTS_DIR / name, 'WEBP', quality=85)
    first = not ProductImage.objects.filter(producto_codigo=code).exists()
    order = ProductImage.objects.filter(producto_codigo=code).count()
    img = ProductImage.objects.create(producto_codigo=code, file=name, order=order, is_primary=first)
    cache.delete('inventory_catalog')  # the cached catalog carries the images
    return img


def delete_photo(code, pk):
    img = ProductImage.objects.filter(producto_codigo=code, pk=pk).first()
    if img is None:
        return False
    img.delete()
    # Only remove the file when nothing else uses it.
    if not ProductImage.objects.filter(file=img.file).exists():
        try:
            os.remove(PRODUCTS_DIR / img.file)
        except FileNotFoundError:
            pass
    if img.is_primary:
        nxt = ProductImage.objects.filter(producto_codigo=code).first()
        if nxt:
            nxt.is_primary = True
            nxt.save(update_fields=['is_primary'])
    cache.delete('inventory_catalog')
    return True
