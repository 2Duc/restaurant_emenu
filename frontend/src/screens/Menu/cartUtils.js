// Hàm thuần của trang Menu (lọc món, tính giỏ) — tách ra để test riêng.
export function filterMenuItems(items, activeCategory, search) {
  return items.filter(item => item.is_available
    && (activeCategory === 'all' || String(item.category) === activeCategory)
    && `${item.name} ${item.description || ''}`.toLowerCase().includes(search.toLowerCase()));
}
export const cartCount = cart => cart.reduce((n, x) => n + x.quantity, 0);
export const cartTotal = cart => cart.reduce((n, x) => n + Number(x.price) * x.quantity, 0);
export function addToCart(current, item) {
  const found = current.find(x => x.id === item.id);
  return found ? current.map(x => x.id === item.id ? { ...x, quantity: x.quantity + 1 } : x)
    : [...current, { id: item.id, name: item.name, price: item.price, quantity: 1 }];
}
export const changeCartQty = (current, id, delta) => current.map(x => x.id === id ? { ...x, quantity: x.quantity + delta } : x).filter(x => x.quantity > 0);
