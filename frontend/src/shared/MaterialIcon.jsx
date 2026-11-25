import styles from "../shared/styles.module.css";

/**
 * Material Symbols Outlined icon helper — shared across all screens.
 * Defaults: 24px, weight 400, grade 0. Decorative (aria-hidden).
 */
export default function MaterialIcon({
  name,
  className = "",
  filled = false,
  style,
  size,
}) {
  const mergedStyle = size ? { ...style, fontSize: size } : style;
  return (
    <span
      className={`${styles.materialIcon} ${filled ? styles.materialIconFilled : ""} ${className}`}
      style={mergedStyle}
      aria-hidden="true"
    >
      {name}
    </span>
  );
}
