"""Parse tham số request an toàn: sai kiểu -> 400 (ValidationError) thay vì 500."""
from rest_framework.exceptions import ValidationError


def int_param(value, name, *, min_value=None, max_value=None):
    """Trả int hoặc None nếu value rỗng/None; sai kiểu hoặc ngoài khoảng -> ValidationError (400)."""
    if value is None or value == '':
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise ValidationError({name: 'Phải là số nguyên.'})
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError({name: 'Phải là số nguyên.'})
    if (min_value is not None and number < min_value) or (max_value is not None and number > max_value):
        raise ValidationError({name: 'Giá trị ngoài phạm vi cho phép.'})
    if abs(number) > 2**62:
        raise ValidationError({name: 'Giá trị ngoài phạm vi cho phép.'})
    return number
