import { useCallback, useRef, useState } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { PromptDialog } from "../components/PromptDialog";

type ConfirmOptions = {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

type PromptOptions = {
  title: string;
  message?: string;
  defaultValue?: string;
  placeholder?: string;
  confirmLabel?: string;
};

export function useConfirmPrompt() {
  const [confirmState, setConfirmState] = useState<
    (ConfirmOptions & { resolve: (ok: boolean) => void }) | null
  >(null);
  const [promptState, setPromptState] = useState<
    (PromptOptions & { resolve: (value: string | null) => void }) | null
  >(null);
  const confirmRef = useRef(confirmState);
  const promptRef = useRef(promptState);
  confirmRef.current = confirmState;
  promptRef.current = promptState;

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setConfirmState({ ...options, resolve });
    });
  }, []);

  const prompt = useCallback((options: PromptOptions) => {
    return new Promise<string | null>((resolve) => {
      setPromptState({ ...options, resolve });
    });
  }, []);

  const closeConfirm = useCallback((ok: boolean) => {
    const state = confirmRef.current;
    if (state) {
      state.resolve(ok);
      setConfirmState(null);
    }
  }, []);

  const closePrompt = useCallback((value: string | null) => {
    const state = promptRef.current;
    if (state) {
      state.resolve(value);
      setPromptState(null);
    }
  }, []);

  const dialogs = (
    <>
      {confirmState && (
        <ConfirmDialog
          title={confirmState.title}
          message={confirmState.message}
          confirmLabel={confirmState.confirmLabel}
          cancelLabel={confirmState.cancelLabel}
          danger={confirmState.danger}
          onConfirm={() => closeConfirm(true)}
          onCancel={() => closeConfirm(false)}
        />
      )}
      {promptState && (
        <PromptDialog
          title={promptState.title}
          message={promptState.message}
          defaultValue={promptState.defaultValue}
          placeholder={promptState.placeholder}
          confirmLabel={promptState.confirmLabel}
          onSubmit={closePrompt}
          onCancel={() => closePrompt(null)}
        />
      )}
    </>
  );

  return { confirm, prompt, dialogs };
}
