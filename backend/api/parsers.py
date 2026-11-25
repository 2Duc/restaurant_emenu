from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class ObjectJSONParser(JSONParser):
    """Chỉ nhận JSON dạng object ({...}); mảng/số/chuỗi ở gốc -> 400 thay vì lỗi 500 khi view gọi request.data.get()."""

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        if not isinstance(data, dict):
            raise ParseError('Dữ liệu gửi lên phải là một đối tượng JSON.')
        return data
