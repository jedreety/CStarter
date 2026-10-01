// Le pont vers bridge.py : chaque appel renvoie {ok} ou {error}, et Python pousse des événements
// par window.cstarter.emit.

export interface BridgeFailure {
  kind: string;
  message: string;
  paths?: string[];
}

export class ApiError extends Error {
  kind: string;
  paths: string[];

  constructor(failure: BridgeFailure) {
    super(failure.message);
    this.kind = failure.kind;
    this.paths = failure.paths ?? [];
  }
}

type Listener = (payload: any) => void;
const listeners = new Map<string, Set<Listener>>();

declare global {
  interface Window {
    pywebview?: { api: Record<string, (...args: unknown[]) => Promise<any>> };
    cstarter: { emit: (name: string, payload: unknown) => void };
  }
}

window.cstarter = {
  emit(name, payload) {
    listeners.get(name)?.forEach(listener => listener(payload));
  }
};

export function on(name: string, listener: Listener): () => void {
  if (!listeners.has(name)) listeners.set(name, new Set());
  listeners.get(name)!.add(listener);
  return () => listeners.get(name)?.delete(listener);
}

const ready = new Promise<void>(resolve => {
  if (window.pywebview?.api) resolve();
  else window.addEventListener('pywebviewready', () => resolve(), { once: true });
});

export async function call<T = unknown>(method: string, ...args: unknown[]): Promise<T> {
  await ready;
  let answer: any;
  try {
    answer = await window.pywebview!.api[method](...args);
  } catch (error: any) {
    // Une erreur que CStarter n'explique pas : pywebview la rejette telle que Python l'a levée.
    throw new ApiError({ kind: error?.name ?? 'Error', message: error?.message ?? String(error) });
  }
  if (answer && typeof answer === 'object' && 'error' in answer) throw new ApiError(answer.error);
  return answer?.ok as T;
}
