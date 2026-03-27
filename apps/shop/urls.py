from django.urls import path
from apps.shop import views

app_name = 'shop'

urlpatterns = [
    # Member-facing
    path('',                                    views.catalog,       name='catalog'),
    path('cart/',                               views.cart_view,     name='cart'),
    path('cart/add/<int:product_pk>/',          views.cart_add,      name='cart_add'),
    path('cart/update/<int:product_pk>/',       views.cart_update,   name='cart_update'),
    path('cart/remove/<int:product_pk>/',       views.cart_remove,   name='cart_remove'),
    path('checkout/',                           views.checkout,      name='checkout'),
    path('orders/',                             views.order_history, name='order_history'),
    path('orders/<int:order_pk>/',              views.order_detail,  name='order_detail'),
]
