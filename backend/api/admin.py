from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    UserAccount, Category, MenuItem, Table,
    Order, OrderItem, Payment, Promotion, Review, StaffCall
)


@admin.register(UserAccount)
class UserAccountAdmin(UserAdmin):
    # Hiện trên danh sách user
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'email')

    # Form thêm / sửa user
    fieldsets = UserAdmin.fieldsets + (
        ('Thông tin thêm', {'fields': ('role',)}),
    )

    # Form tạo user mới
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Thông tin thêm', {'fields': ('role',)}),
    )

# Register your models here.
# admin.site.register(UserAccount)
admin.site.register(Category)
admin.site.register(MenuItem)
admin.site.register(Table)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Review)
admin.site.register(Payment)
admin.site.register(Promotion)
admin.site.register(StaffCall)
