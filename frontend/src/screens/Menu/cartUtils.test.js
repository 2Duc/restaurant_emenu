import { describe, expect, it } from 'vitest';
import { addToCart, cartCount, cartTotal, changeCartQty, filterMenuItems } from './cartUtils';

const items = [
  { id: 1, name: 'Phở bò', description: 'Nước dùng xương', category: 1, is_available: true },
  { id: 2, name: 'Cơm tấm', description: '', category: 2, is_available: true },
  { id: 3, name: 'Bún chả', description: null, category: 1, is_available: false },
];

describe('filterMenuItems', () => {
  it('hides unavailable items', () => {
    // Món hết (is_available=false) không hiển thị
    expect(filterMenuItems(items, 'all', '').map(i => i.id)).toEqual([1, 2]);
  });
  it('filters by category id given as string', () => {
    // Lọc theo danh mục (id dạng chuỗi)
    expect(filterMenuItems(items, '2', '').map(i => i.id)).toEqual([2]);
  });
  it('searches name and description case-insensitively', () => {
    // Tìm không phân biệt hoa thường, cả trong mô tả
    expect(filterMenuItems(items, 'all', 'PHỞ').map(i => i.id)).toEqual([1]);
    expect(filterMenuItems(items, 'all', 'xương').map(i => i.id)).toEqual([1]);
  });
  it('returns empty list when nothing matches', () => {
    // Không khớp -> mảng rỗng
    expect(filterMenuItems(items, 'all', 'zzz')).toEqual([]);
  });
});

describe('cart helpers', () => {
  it('addToCart adds a new line with quantity 1', () => {
    // Thêm món mới -> dòng số lượng 1
    expect(addToCart([], { id: 1, name: 'A', price: '100', extra: 1 })).toEqual([{ id: 1, name: 'A', price: '100', quantity: 1 }]);
  });
  it('addToCart increments an existing line without mutating input', () => {
    // Thêm món đã có -> tăng số lượng, không sửa mảng cũ
    const cart = [{ id: 1, name: 'A', price: 10, quantity: 1 }];
    const next = addToCart(cart, { id: 1 });
    expect(next[0].quantity).toBe(2);
    expect(cart[0].quantity).toBe(1);
  });
  it('changeCartQty removes a line when quantity reaches 0', () => {
    // Giảm về 0 -> xoá dòng
    expect(changeCartQty([{ id: 1, quantity: 1 }], 1, -1)).toEqual([]);
    expect(changeCartQty([{ id: 1, quantity: 1 }, { id: 2, quantity: 2 }], 2, -1)).toEqual([{ id: 1, quantity: 1 }, { id: 2, quantity: 1 }]);
  });
  it('cartCount and cartTotal sum quantities and price*quantity', () => {
    // Tổng số lượng và tổng tiền (giá dạng chuỗi Decimal)
    const cart = [{ price: '85000', quantity: 2 }, { price: 15000, quantity: 3 }];
    expect(cartCount(cart)).toBe(5);
    expect(cartTotal(cart)).toBe(215000);
    expect(cartCount([])).toBe(0);
    expect(cartTotal([])).toBe(0);
  });
});
