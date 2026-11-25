from django.urls import re_path
from .consumers import RestaurantConsumer
websocket_urlpatterns = [re_path(r'^ws/(?P<group_name>kitchen_orders|staff_orders|table_[0-9]+)/$', RestaurantConsumer.as_asgi())]
