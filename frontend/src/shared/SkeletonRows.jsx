/** Dòng khung chờ khi danh sách quản lý đang tải lần đầu. */
export default function SkeletonRows({ rows = 5 }) {
  return <div aria-busy="true" aria-label="Đang tải" style={{ display: 'grid', gap: 'var(--sp-3)', padding: 'var(--sp-4)' }}>
    {Array.from({ length: rows }, (_, i) => <span key={i} className="skeleton" style={{ height: 20, width: `${95 - (i % 3) * 12}%` }} />)}
  </div>;
}
