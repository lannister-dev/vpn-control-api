import { Modal } from "./Modal.jsx";
import { Icon } from "./Icon.jsx";

export function ConfirmModal({
  title = "Подтверждение",
  body,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  tone = "primary",
  icon,
  loading = false,
  onConfirm,
  onClose,
}) {
  const confirmCls = tone === "danger" ? "btn btn-danger" : "btn btn-primary";
  return (
    <Modal
      title={title}
      onClose={loading ? () => {} : onClose}
      footer={
        <>
          <button className="btn" disabled={loading} onClick={onClose}>{cancelLabel}</button>
          <button
            className={confirmCls}
            disabled={loading}
            onClick={onConfirm}
          >
            {icon && <Icon name={icon} size={13} />} {confirmLabel}
          </button>
        </>
      }
    >
      <div style={{ lineHeight: 1.5 }}>{body}</div>
    </Modal>
  );
}
