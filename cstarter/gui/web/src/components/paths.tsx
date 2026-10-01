// Les chemins du projet : relatifs à sa racine, à barres obliques. L'icône de dossier
// ouvre la boîte de Windows ; le texte reste modifiable. Dans une source téléchargée, l'arbre de ses
// dossiers tient lieu de boîte.

import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import { ArrowRight01Icon, Cancel01Icon, File01Icon, FileAddIcon, Folder01Icon, FolderAddIcon, Tick02Icon } from '@hugeicons/core-free-icons';
import { pickPaths } from '../lib/actions';
import { t } from '../lib/i18n';
import { MenuButton, Popover } from './Popover';
import { Button, Icon, TextField, TokenList } from './ui';
import './paths.css';

type Kind = 'folder' | 'file';

const slashes = (path: string) => path.trim().replace(/\\/g, '/');

export function PathField({
  value,
  onCommit,
  kind = 'folder',
  placeholder,
  types
}: {
  value: string;
  onCommit: (value: string) => void;
  kind?: Kind;
  placeholder?: string;
  types?: string[];
}) {
  const pick = async () => {
    const chosen = await pickPaths(kind, value || undefined, false, types);
    if (chosen) onCommit(chosen[0]);
  };
  return (
    <div className="path">
      <TextField value={value} mono placeholder={placeholder} onCommit={v => onCommit(slashes(v))} className="path__text" />
      <Button tone="ghost" size="sm" icon={kind === 'folder' ? Folder01Icon : File01Icon} title={kind === 'folder' ? t('Choisir un dossier', 'Choose a folder') : t('Choisir un fichier', 'Choose a file')} onClick={pick} />
    </div>
  );
}

// Une liste de chemins : chacun se retire, l'icône en ajoute par la boîte de Windows, plusieurs d'un
// coup. adapt change ce qui est choisi : un dossier exclu devient le motif de tout ce qu'il contient.
export function PathList({
  values,
  onChange,
  kinds = ['folder'],
  typed = false,
  placeholder,
  adapt = path => path
}: {
  values: string[];
  onChange: (values: string[]) => void;
  kinds?: Kind[];
  typed?: boolean;
  placeholder?: string;
  adapt?: (path: string, kind: Kind) => string;
}) {
  const add = async (kind: Kind) => {
    const chosen = await pickPaths(kind, undefined, true);
    if (!chosen) return;
    const next = [...values];
    for (const path of chosen.map(p => adapt(p, kind))) if (!next.includes(path)) next.push(path);
    onChange(next);
  };
  const picker =
    kinds.length > 1 ? (
      <MenuButton
        icon={FolderAddIcon}
        title={t('Ajouter', 'Add')}
        align="start"
        width={190}
        items={[
          { value: 'folder', label: t('Dossier', 'Folder'), icon: Folder01Icon },
          { value: 'file', label: t('Fichier', 'File'), icon: File01Icon }
        ]}
        onSelect={kind => add(kind as Kind)}
      />
    ) : (
      <Button tone="ghost" size="sm" icon={kinds[0] === 'folder' ? FolderAddIcon : FileAddIcon} title={kinds[0] === 'folder' ? t('Ajouter un dossier', 'Add a folder') : t('Ajouter un fichier', 'Add a file')} onClick={() => add(kinds[0])} />
    );
  return <TokenList values={values} onChange={next => onChange(next.map(slashes))} typed={typed} placeholder={placeholder} extra={picker} />;
}

// Ce que les builders manual et none désignent dans une source, et comment le montrer.
export type Want = 'headers' | 'lib' | 'dll';
const EXTENSIONS: Record<Want, string> = { headers: '.h', lib: '.lib', dll: '.dll' };

const parentOf = (path: string) => (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '.');

// Un dossier d'une source téléchargée, choisi dans l'arbre de ses dossiers.
export function SourceFolder({
  folders,
  value,
  onChange,
  want,
  root,
  optional
}: {
  folders: Record<string, string[]>;
  value: string | null;
  onChange: (value: string | null) => void;
  want: Want;
  root: string;
  optional?: boolean;
}) {
  const anchor = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  return (
    <div className="designation">
      <button ref={anchor} type="button" className={`designation__value${value === null ? ' designation__value--empty' : ''}`} aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon icon={Folder01Icon} size={14} />
        <span className="mono">{value === null ? t('Aucun', 'None') : value === '.' ? root : value}</span>
      </button>
      {optional && value !== null ? <Button tone="ghost" size="sm" icon={Cancel01Icon} title={t('Retirer', 'Remove')} onClick={() => onChange(null)} /> : null}
      <Popover anchor={anchor} open={open} onClose={close} width={340}>
        <FolderTree
          folders={folders}
          value={value}
          want={want}
          root={root}
          onPick={path => {
            setOpen(false);
            onChange(path);
          }}
        />
      </Popover>
    </div>
  );
}

function FolderTree({ folders, value, want, root, onPick }: { folders: Record<string, string[]>; value: string | null; want: Want; root: string; onPick: (path: string) => void }) {
  const children = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const path of Object.keys(folders).sort((a, b) => a.localeCompare(b))) {
      if (path === '.') continue;
      const parent = parentOf(path);
      if (!map.has(parent)) map.set(parent, []);
      map.get(parent)!.push(path);
    }
    return map;
  }, [folders]);
  // L'arbre s'ouvre jusqu'au dossier choisi et jusqu'à ceux qui contiennent ce qu'on cherche.
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const open = new Set(['.']);
    const reach = (path: string) => {
      for (let current = path; current !== '.'; ) open.add((current = parentOf(current)));
    };
    Object.entries(folders).forEach(([path, kinds]) => kinds.includes(want) && reach(path));
    if (value) reach(value);
    return open;
  });
  const toggle = (path: string) =>
    setExpanded(current => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const rows = (path: string, depth: number): ReactNode[] => {
    const kids = children.get(path) ?? [];
    const open = expanded.has(path);
    const name = path === '.' ? root : path.slice(path.lastIndexOf('/') + 1);
    return [
      <div key={path} className={`tree__row${path === value ? ' tree__row--on' : ''}`} style={{ paddingLeft: 6 + depth * 16 }}>
        <button type="button" className="tree__toggle" tabIndex={-1} disabled={!kids.length} onClick={() => toggle(path)}>
          {kids.length ? <Icon icon={ArrowRight01Icon} size={12} stroke={2.2} className={`tree__chevron${open ? ' tree__chevron--open' : ''}`} /> : null}
        </button>
        <button type="button" className="tree__pick" onClick={() => onPick(path)}>
          <Icon icon={Folder01Icon} size={14} className="tree__icon" />
          <span className="tree__name">{name}</span>
          {folders[path]?.includes(want) ? <span className="tree__kind">{EXTENSIONS[want]}</span> : null}
          {path === value ? <Icon icon={Tick02Icon} size={13} stroke={2.4} className="tree__check" /> : null}
        </button>
      </div>,
      ...(open ? kids.flatMap(kid => rows(kid, depth + 1)) : [])
    ];
  };
  return <div className="tree">{rows('.', 0)}</div>;
}

// Les exemples, les tests, la documentation et les dépendances tierces d'une source ne sont pas la
// bibliothèque : les GLFW des exemples d'imgui, par exemple.
const ASIDE = /(^|\/)(examples?|samples?|tests?|testing|docs?|demos?|benchmarks?|third[_-]?party|3rdparty|externals?|extern|vendor|deps)(\/|$)/i;

// Le dossier le plus probable pour ce qu'on cherche. Pour les headers, le moins profond qui s'appelle
// include ou qui en contient : la racine d'une bibliothèque sans dossier include/, comme imgui. Pour
// les .lib et les .dll, celui dont le chemin nomme la plateforme, le seul qui en contienne, ou celui du
// Visual Studio le plus récent : lib-vc2022 plutôt que lib-vc2019.
export function guessFolder(folders: Record<string, string[]>, want: Want, platform?: string): string | null {
  const depth = (path: string) => (path === '.' ? 0 : path.split('/').length);
  const all = Object.keys(folders).filter(path => !ASIDE.test(path));
  if (want === 'headers') {
    const named = (path: string) => /^(single_)?include$/i.test(path.slice(path.lastIndexOf('/') + 1));
    const candidates = all.filter(path => named(path) || folders[path].includes('headers'));
    return candidates.sort((a, b) => depth(a) - depth(b) || Number(named(b)) - Number(named(a)) || a.localeCompare(b))[0] ?? null;
  }
  const holding = all.filter(path => folders[path].includes(want)).sort((a, b) => depth(a) - depth(b) || a.localeCompare(b));
  const aliases: Record<string, RegExp> = {
    x64: /(^|[/_-])(x64|win64|amd64|x86_64|64)([/_-]|$)/i,
    x86: /(^|[/_-])(x86(?!_64)|win32|ia32|i386|32)([/_-]|$)/i,
    ARM64: /(^|[/_-])(arm64|aarch64)([/_-]|$)/i
  };
  const named = platform ? holding.filter(path => aliases[platform]?.test(path)) : [];
  if (named.length || holding.length === 1) return named[0] ?? holding[0];
  const year = (path: string) => Math.max(0, ...(path.match(/20\d\d/g) ?? []).map(Number));
  return holding.filter(year).sort((a, b) => year(b) - year(a))[0] ?? null;
}
