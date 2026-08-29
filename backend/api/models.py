from django.db import models

# Create your models here.
class Product(models.Model):

    BRAND_CHOICES = [
        ('GEA', 'GEA'),
        ('Bionat Sano', 'Bionat Sano'),
        ('Animat', 'Animat'),
        ('VES-Artex', 'VES-Artex'),
    ]
    
    CATEGORY_CHOICES = [
        ('Sistemas de Ordeño', 'Sistemas de Ordeño'),
        ('Nutrición', 'Nutrición'),
        ('Refacciones', 'Refacciones'),
        ('Confort Animal', 'Confort Animal'),
        ('Almacenamiento', 'Almacenamiento'),
    ]

    brand = models.CharField(max_length=50, choices=BRAND_CHOICES, default='GEA')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='Refacciones')

    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.name} - {self.sku}"

class StockMovement(models.Model):
    MOVEMENT_CHOICES = [
        ('ENTRADA', 'Entrada (Compra)'),
        ('SALIDA', 'Salida (Consumo)'),
    ]

    # ForeignKey conecta este movimiento con un producto específico de tu tabla principal
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    movement_type = models.CharField(max_length=10, choices=MOVEMENT_CHOICES)
    quantity = models.PositiveIntegerField()
    # auto_now_add guarda la fecha y hora exacta del momento en que se registra
    date = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=255, help_text="Ej. Consumo diario, Orden de compra #123")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.movement_type == "ENTRADA":
            self.product.stock += self.quantity
        elif self.movement_type == "SALIDA":
            self.product.stock -= self.quantity

        self.product.save()

         

    def __str__(self):
        return f"{self.movement_type} | {self.product.name} | Cantidad: {self.quantity}"