// L'état de l'interface, en un seul objet : la page le lit par useStore, les actions le changent.

import { useRef, useSyncExternalStore, type ReactNode } from 'react';
import type { Language } from './i18n';
import type { Dependency, GitStatus, Prerequisite, Project, Recent, View } from './model';

export type Tone = 'info' | 'success' | 'danger';

export interface Toast {
  id: number;
  title: string;
  description?: string;
  tone: Tone;
}

// Une opération longue : id sert à EXPECTED (la durée attendue), label à l'affichage.
export interface Run {
  id: number;
  kind: string;
  name: string;
  argument: string;
  status: 'running' | 'done' | 'error';
}

export type PairStatus = 'pending' | 'running' | 'done' | 'failed';

export interface Pair {
  configuration: string;
  platform: string;
  status: PairStatus;
}

export interface Sheet {
  id: number;
  render: (close: (value: unknown) => void) => ReactNode;
  resolve: (value: unknown) => void;
  width?: number;
}

// Le programme lancé par Exécuter, dans l'onglet Programme : son numéro, son target, et son code de
// sortie une fois fini.
export interface Program {
  run: number;
  target: string;
  code: number | null;
}

export type PanelTab = 'output' | 'terminal' | 'program';

export interface State {
  booted: boolean;
  view: View | null;
  page: string;
  // Sans projet ouvert : l'accueil, les bibliothèques du cache, ou la création d'un projet.
  home: 'start' | 'libraries' | 'create';
  recent: Recent[];
  run: Run | null;
  matrix: Pair[] | null;
  // height vaut null tant que l'utilisateur ne l'a pas réglée : elle suit alors la fenêtre.
  panel: { open: boolean; tab: PanelTab; height: number | null };
  toasts: Toast[];
  git: GitStatus | null | undefined;
  cache: Dependency[] | null;
  maximized: boolean;
  sheets: Sheet[];
  busy: boolean;
  pair: { configuration: string; platform: string } | null;
  terminalAlive: boolean;
  program: Program | null;
  epoch: number;
  update: string | null;
  prerequisites: Prerequisite[] | null;
  language: Language;
  version: string;
  // Le compte GitHub que l'accueil salue : undefined tant qu'on ne le sait pas, null sans compte.
  github: string | null | undefined;
}

let state: State = {
  booted: false,
  view: null,
  page: 'overview',
  home: 'start',
  recent: [],
  run: null,
  matrix: null,
  panel: { open: false, tab: 'output', height: null },
  toasts: [],
  git: undefined,
  cache: null,
  maximized: false,
  sheets: [],
  busy: false,
  pair: null,
  terminalAlive: false,
  program: null,
  epoch: 0,
  update: null,
  prerequisites: null,
  language: 'fr',
  version: '',
  github: undefined
};

const subscribers = new Set<() => void>();

export function getState(): State {
  return state;
}

export function setState(patch: Partial<State> | ((current: State) => Partial<State>)): void {
  state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) };
  subscribers.forEach(notify => notify());
}

function subscribe(notify: () => void): () => void {
  subscribers.add(notify);
  return () => subscribers.delete(notify);
}

export function useStore<T>(select: (current: State) => T): T {
  return useSyncExternalStore(subscribe, () => select(state));
}

// Le projet ouvert. Une page qui s'efface après la fermeture du projet garde le dernier qu'elle a vu,
// le temps de son animation de sortie.
export function useProject(): Project {
  const project = useStore(s => s.view?.project ?? null);
  const last = useRef(project);
  if (project) last.current = project;
  return last.current!;
}

// La hauteur du panneau du bas : celle que l'utilisateur a réglée, sinon trois dixièmes de la
// fenêtre, entre 150 et 340 pixels ; jamais plus de sept dixièmes.
export function panelHeight(height: number | null, window: number): number {
  const wanted = height ?? Math.round(Math.min(340, Math.max(150, window * 0.3)));
  return Math.max(150, Math.min(wanted, Math.round(window * 0.72)));
}

function onResize(notify: () => void): () => void {
  window.addEventListener('resize', notify);
  return () => window.removeEventListener('resize', notify);
}

// La hauteur de la fenêtre, qui redessine qui la lit quand elle change.
export function useWindowHeight(): number {
  return useSyncExternalStore(onResize, () => window.innerHeight);
}
