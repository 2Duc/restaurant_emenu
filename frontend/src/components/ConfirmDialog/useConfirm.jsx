import { useCallback, useRef, useState } from 'react';
import { ConfirmDialog } from './ConfirmDialog';

/** const [confirm, confirmDialog] = useConfirm(); if (!await confirm('...')) return; — nhớ render {confirmDialog}. */
export function useConfirm() {
  const [state, setState] = useState(null);
  const resolver = useRef(null);
  const confirm = useCallback((message, opts = {}) => new Promise(resolve => { resolver.current = resolve; setState({ message, ...opts }); }), []);
  const close = result => { resolver.current?.(result); resolver.current = null; setState(null); };
  const dialog = state && <ConfirmDialog {...state} onConfirm={() => close(true)} onCancel={() => close(false)} />;
  return [confirm, dialog];
}
