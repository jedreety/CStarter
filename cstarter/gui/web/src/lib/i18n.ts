// La langue de l'interface : chaque texte porte ses deux versions,
// t('français', 'english'). Le choix vient de bridge.py, qui le partage avec la ligne de commande ;
// la fenêtre se redessine quand il change.

export type Language = 'fr' | 'en';

let current: Language = 'fr';

export function language(): Language {
  return current;
}

export function setLanguage(next: Language): void {
  current = next;
  document.documentElement.lang = next;
}

export function t(fr: string, en: string): string {
  return current === 'en' ? en : fr;
}

// Un nombre et son nom accordé : le français met le pluriel à partir de deux, l'anglais dès que le
// nombre n'est pas un.
export function count(n: number, fr: [string, string], en: [string, string]): string {
  return current === 'en' ? `${n} ${n === 1 ? en[0] : en[1]}` : `${n} ${n > 1 ? fr[1] : fr[0]}`;
}
