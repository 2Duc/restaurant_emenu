import { useEffect, useRef } from "react";
import MaterialIcon from "./MaterialIcon";

/**
 * Floating toast notification — shared by Menu, Chef, Manager.
 */
export default function Toast({
  message,
  icon = "check_circle",
  visible,
  onHide,
  duration = 2800,
}) {
  const timerRef = useRef(null);

  useEffect(() => {
    if (!visible) return undefined;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      if (onHide) onHide();
    }, duration);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [visible, message, duration, onHide]);

  return (
    <div
      className={`toast toast-ok ${visible ? "" : "toast-hidden"}`}
      role="status"
    >
      <MaterialIcon name={icon} className="toast-icon" size={20} />
      <span>{message}</span>
    </div>
  );
}
