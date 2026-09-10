import os
import re
import shutil

from django.core.management.base import BaseCommand

from api.models import AdmProductos
from catalog.models import ProductImage

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PRODUCTS_DIR = os.path.join(BACKEND_DIR, "..", "frontend", "public", "products")
CATALOGO_DIR = os.path.join(PRODUCTS_DIR, "catalogo")

STRICT_GEA_CODE_RE = re.compile(r"^\d{4}-\d{4}-\d{3}$")

EXCLUDE_FILES = {
    "Aceites_Aceites.jpg",
    "Bionat-Sano_Catálogo_Bionat-Sano.png",
    "Bovinos_de_Carne_Bovinos_de_Carne.jpg",
    "Bovinos_de_Leche_Bovinos_de_Leche.jpg",
    "Detergentes_Especiales_Detergentes_Especiales.jpg",
    "Detergentes_Nacionales_Detergentes_Nacionales.jpg",
    "Detergentes_Westfalia_Detergentes_Westfalia.jpg",
    "Ovinos_y_Caprinos_Ovinos_y_Caprinos.jpg",
    "Presellos_Surge_Presellos_Surge.jpg",
    "Refacciones_Importadas_Refacciones_Importadas.jpg",
    "Selladores_Surge_Selladores_Surge.jpg",
    "unnamed_product.jpg",
    # Unregistered in the ERP (GEA-code filenames with no matching product) or
    # deferred for manual review later. See backend/scripts/catalogo_deferred.csv.
    "0004-1659-880.png",
    "0007-3239-890.png",
    "0013-0294-300.png",
    "0013-0403-400.png",
    "0018-1484-7000.png",
    "4562-0001-026.png",
    "4999-1022-041.jpg",
    "4999-1022-044.jpg",
    "4999-1070-172.png",
    "4999-1081-132.jpg",
    "4999-1090-005.png",
    "4999-1160-527.png",
    "7015-1797-020.png",
    "7021-2088-080.png",
    "7021-2447-020.png",
    "7021-2620-450.png",
    "7025-2629-010.jpg",
    "7025-2721-000.png",
    "7025-2721-010.png",
    "7036-6206-030.png",
    "7038-9905-020.jpg",
    "7041-2745-010.png",
    "7047-1350-189.png",
    "7049-1150-460.png",
    "7051-1703-000.png",
    "7051-9926-000.png",
    "7071-2084-050.jpg",
    "7161-1734-040.png",
    "7161-2479-070.png",
    "7751-004-071.png",
    "7751-0040-01P.png",
    "7751-0040-287.png",
    "7751-0042-212.png",
    "Sanolac_Lamb_25_kg.png",  # no 25kg SKU exists in the ERP
    "Iniciador_para_Corderos.png",  # deferred for manual matching
}

# Human-reviewed corrections: fuzzy match's top guess was wrong.
FUZZY_OVERRIDES = {
    "Bovifit_1_kg.png": ["BIO-BOVI"],
    "Bovifit_1_kg_2.png": ["BIO-BOVI"],
    "Kristall_Hefe_10_kg.png": ["BIO-KRI1"],
    "Kristall_Hefe_10_kg_2.png": ["BIO-KRI1"],
    "Kristall_Hefe_25_kg.png": ["BIO-KRIH"],
    "Milsan_25_kg.png": ["BIO-MIL2"],
    "Ovisan_Engorda_Pro.png": ["BIO-OVEP"],
    "Sanolac_Lila_Citro.png": ["BIO-SLC2", "BIO-SLC1"],  # same photo, both sizes
}

# Human-reviewed: fuzzy match's top guess was accepted as correct.
FUZZY_ACCEPTED = {
    "Aceite_Turbina_05_Litros_ACERTUV.png": "ACETURV",
    "Aceite_Turbina_10_Litros_ACERTUV.png": "ACETURV",
    "Aceite_Turbina_20_Litros_ACERTUV.png": "ACETURV",
    "Alimento_Preiniciador_Meggi_100_40_kg.png": "BIO-ME1E",
    "Alimento_Preiniciador_Meggi_100_E_40_kg.png": "BIO-ME1E",
    "Cloro_13_240_Kg_0101013.png": "0101013",
    "Cloro_13_30_Kg_0101012.png": "0101012",
    "Concentrado_Meggi_100_E_40_kg.png": "BIO-ME1E",
    "Concentrado_Proteico_Meggi_40_40_kg.png": "BIO-MEG42",
    "Lateccino_Pro_cubeta_2.5_kg.png": "BIO-LAT2",
    "Latteccino_Pro_10_kg.png": "BIO-LAP1",
    "Mipro_150.png": "BIO-M150",
    "Mipro_150_2.png": "BIO-M150",
    "Mipro_250.png": "BIO-M250",
    "Mipro_250_Eco.png": "BIO-ME25",
    "Mipro_250_Monensina.png": "BIO-MM25",
    "Mipro_Bull_150.png": "BIO-MB15",
    "Mipro_Bull_150_E_25_kg-producción.png": "BIO-MB1E",
    "Mipro_Bull_150_E_Forte_30_kg.png": "BIO-MB1EF",
    "Mipro_Bull_150_Monensina_25_kg.png": "BIO-MB1M",
    "Mipro_Bull_150_Monensina_25_kg_2.png": "BIO-MB1M",
    "Mipro_Bull_150_Monensina_Cromo_25_kg.png": "BIO-MB1M",
    "Mipro_Bull_150_Monensina_Z_25_kg.png": "BIO-MB1M",
    "Mipro_Energizer_25_kg.png": "BIO-MEN2",
    "Mipro_Energizer_25_kg_2.png": "BIO-MEN2",
    "Mipro_Energizer_4_kg.png": "BIO-MENE",
    "Mipro_Energizer_4_kg_2.png": "BIO-MENE",
    "Mipro_M_500_25_kg.png": "BIO-M500",
    "Mipro_M_500_Monensina_25_kg.png": "BIO-MM50",
    "Mipro_Ovi_50.png": "BIO-MOV5",
    "Mipro_Pren_400.png": "BIO-CMP40",
    "Ovisan_Engorda_20_kg.png": "BIO-OENG",
    "Ovisan_Engorda_CA.png": "BIO-OECA",
    "Redstar_Detergente_Alcalino_Clorado_30_Kg_0108003.png": "0108003",
    "Redstar_Yodo_Vita_1.75_10_Kg_0101075.png": "0101075",
    "Redstar_Yodo_Vita_1.75_25_Kg_0101076.png": "0101076",
    "Sanolac_Lamb_Cubeta.png": "BIO-LAM2",
}


class Command(BaseCommand):
    help = (
        "Rebuilds ProductImage from the human-reviewed catalogo/ mapping. "
        "Backfills a row for every existing frontend/public/products/*.webp, "
        "then imports the resolved catalogo/ files. Idempotent: clears and "
        "rebuilds ProductImage each run. Writes only to the local 'default' "
        "DB and to frontend/public/products/ on disk - never touches the ERP."
    )

    def handle(self, *args, **options):
        codes = set(AdmProductos.objects.values_list("CCODIGOPRODUCTO", flat=True))
        code_by_lower = {c.lower(): c for c in codes}

        ProductImage.objects.all().delete()
        next_order = {}  # code -> next order value to assign
        codes_with_webp = set()

        def add_image(code, filename, seed_primary=False):
            order = next_order.get(code, 0)
            ProductImage.objects.create(
                producto_codigo=code,
                file=filename,
                order=order,
                is_primary=(order == 0) if not seed_primary else True,
            )
            next_order[code] = order + 1

        # 1) Backfill existing .webp files (these are already the primary image).
        existing_webps = sorted(f for f in os.listdir(PRODUCTS_DIR) if f.endswith(".webp"))
        for filename in existing_webps:
            code = os.path.splitext(filename)[0]
            add_image(code, filename, seed_primary=True)
            codes_with_webp.add(code)
        self.stdout.write(f"Backfilled {len(existing_webps)} existing .webp images.")

        # 2) Import catalogo/ files per the reviewed mapping.
        all_files = sorted(f for f in os.listdir(CATALOGO_DIR) if os.path.isfile(os.path.join(CATALOGO_DIR, f)))
        imported, skipped_duplicate, skipped_excluded = 0, 0, 0

        for filename in all_files:
            if filename in EXCLUDE_FILES:
                skipped_excluded += 1
                continue

            stem = os.path.splitext(filename)[0]

            if filename in FUZZY_OVERRIDES:
                target_codes = FUZZY_OVERRIDES[filename]
            elif filename in FUZZY_ACCEPTED:
                target_codes = [FUZZY_ACCEPTED[filename]]
            elif stem.lower() in code_by_lower:
                target_codes = [code_by_lower[stem.lower()]]
            else:
                raise ValueError(f"Unhandled file with no mapping decision: {filename}")

            is_strict_gea_code = bool(STRICT_GEA_CODE_RE.match(stem))

            for code in target_codes:
                if is_strict_gea_code and code in codes_with_webp:
                    skipped_duplicate += 1
                    continue
                shutil.copy2(os.path.join(CATALOGO_DIR, filename), os.path.join(PRODUCTS_DIR, filename))
                add_image(code, filename)
                imported += 1

        self.stdout.write(f"Imported {imported} catalogo images.")
        self.stdout.write(f"Skipped {skipped_duplicate} GEA-code duplicates (already had a .webp of the same picture).")
        self.stdout.write(f"Skipped {skipped_excluded} excluded/unregistered files.")
        self.stdout.write(f"Total ProductImage rows: {ProductImage.objects.count()}")
