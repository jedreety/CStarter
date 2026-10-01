// Ce qui s'ouvre depuis un bouton : un menu, un arbre de dossiers. La surface naît de son bouton,
// dessous, ou dessus faute de place, et se ferme par Échap, par un clic ailleurs ou quand la page
// défile. Rendue dans le body, aucune zone qui défile ne la coupe.

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent as KeyEvent, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import type { IconSvgElement } from '@hugeicons/react';
import { Search01Icon } from '@hugeicons/core-free-icons';
import { t } from '../lib/i18n';
import { Button, Icon } from './ui';
import './Popover.css';

const GAP = 6;
const MARGIN = 10;

interface Place {
  left: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
  origin: string;
}

export function Popover({
  anchor,
  open,
  onClose,
  children,
  width,
  align = 'start',
  className = ''
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  width?: number;
  align?: 'start' | 'end';
  className?: string;
}) {
  const surface = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<Place | null>(null);

  // La place se mesure avant le premier affichage : la surface rendue, puis posée.
  useLayoutEffect(() => {
    if (!open) return;
    const trigger = anchor.current?.getBoundingClientRect();
    const menu = surface.current;
    if (!trigger || !menu) return;
    const below = window.innerHeight - trigger.bottom - GAP - MARGIN;
    const above = trigger.top - GAP - MARGIN;
    const down = menu.scrollHeight <= below || below >= above;
    const w = menu.offsetWidth;
    const left = Math.max(MARGIN, Math.min(align === 'end' ? trigger.right - w : trigger.left, window.innerWidth - w - MARGIN));
    setPlace({
      left,
      top: down ? trigger.bottom + GAP : undefined,
      bottom: down ? undefined : window.innerHeight - trigger.top + GAP,
      maxHeight: down ? below : above,
      origin: `${align === 'end' ? 'right' : 'left'} ${down ? 'top' : 'bottom'}`
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const inside = (target: EventTarget | null) => surface.current?.contains(target as Node) || anchor.current?.contains(target as Node);
    const down = (event: PointerEvent) => {
      if (!inside(event.target)) onClose();
    };
    const key = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.stopImmediatePropagation(); // une feuille ouverte dessous reste ouverte
      event.preventDefault();
      onClose();
      anchor.current?.focus({ preventScroll: true });
    };
    const scroll = (event: Event) => {
      if (!surface.current?.contains(event.target as Node)) onClose();
    };
    window.addEventListener('pointerdown', down, true);
    window.addEventListener('keydown', key, true);
    window.addEventListener('scroll', scroll, true);
    window.addEventListener('resize', onClose);
    return () => {
      window.removeEventListener('pointerdown', down, true);
      window.removeEventListener('keydown', key, true);
      window.removeEventListener('scroll', scroll, true);
      window.removeEventListener('resize', onClose);
    };
  }, [open, onClose]);

  return createPortal(
    <AnimatePresence>
      {open ? (
        <motion.div
          ref={surface}
          className={`popover ${className}`}
          style={{
            width,
            left: place?.left ?? -9999,
            top: place ? place.top : -9999,
            bottom: place?.bottom,
            maxHeight: place?.maxHeight,
            transformOrigin: place?.origin,
            visibility: place ? 'visible' : 'hidden'
          }}
          initial={{ opacity: 0, scale: 0.95, filter: 'blur(8px)' }}
          animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, scale: 0.97, filter: 'blur(6px)', transition: { duration: 0.12 } }}
          transition={{ type: 'spring', bounce: 0, duration: 0.24 }}
        >
          {children}
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body
  );
}

export interface MenuItem {
  value: string;
  label: ReactNode;
  icon?: IconSvgElement;
  tag?: ReactNode;
  // Le texte que le filtre cherche, quand label n'en est pas.
  text?: string;
  // Toujours visible, même filtré : « Installer une bibliothèque », par exemple.
  sticky?: boolean;
  separated?: boolean;
  mono?: boolean;
  // Les éléments d'un même groupe se suivent, sous son nom.
  group?: string;
}

// Une liste où choisir, au clavier comme à la souris. filter ajoute un champ qui la restreint.
export function Menu({
  items,
  onSelect,
  filter = false,
  placeholder,
  empty
}: {
  items: MenuItem[];
  onSelect: (value: string) => void;
  filter?: boolean;
  placeholder?: string;
  empty?: ReactNode;
}) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const pill = useId();
  const list = useRef<HTMLDivElement>(null);
  const search = query.trim().toLowerCase();
  const shown = items.filter(item => item.sticky || !search || (item.text ?? String(item.label)).toLowerCase().includes(search));
  const current = Math.min(active, shown.length - 1);

  useEffect(() => {
    if (!filter) list.current?.focus({ preventScroll: true });
  }, []);
  useEffect(() => {
    list.current?.querySelector('[data-active]')?.scrollIntoView({ block: 'nearest' });
  }, [current]);

  const onKey = (event: KeyEvent) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive((current + step + shown.length) % Math.max(1, shown.length));
    } else if (event.key === 'Enter' && shown[current]) {
      event.preventDefault();
      onSelect(shown[current].value);
    }
  };

  return (
    <div className="menu" onKeyDown={onKey}>
      {filter ? (
        <label className="menu__search">
          <Icon icon={Search01Icon} size={14} />
          <input
            autoFocus
            value={query}
            placeholder={placeholder ?? t('Rechercher', 'Search')}
            spellCheck={false}
            onChange={event => {
              setQuery(event.target.value);
              setActive(0);
            }}
          />
        </label>
      ) : null}
      <div className="menu__list" ref={list} tabIndex={-1} role="listbox">
        {shown.map((item, i) => (
          <div key={item.value} className={item.separated && i > 0 ? 'menu__separated' : undefined}>
            {item.group && item.group !== shown[i - 1]?.group ? <div className="menu__group">{item.group}</div> : null}
            <button
              type="button"
              role="option"
              aria-selected={i === current}
              data-active={i === current ? '' : undefined}
              className="menu__item"
              onPointerMove={() => i !== current && setActive(i)}
              onClick={() => onSelect(item.value)}
            >
              {i === current ? <motion.span layoutId={pill} className="menu__pill" transition={{ type: 'spring', bounce: 0, duration: 0.24 }} /> : null}
              {item.icon ? <Icon icon={item.icon} size={15} className="menu__icon" /> : null}
              <span className={`menu__label${item.mono ? ' mono' : ''}`}>{item.label}</span>
              {item.tag !== undefined ? <span className="menu__tag">{item.tag}</span> : null}
            </button>
          </div>
        ))}
        {!shown.length && empty ? <div className="menu__empty">{empty}</div> : null}
      </div>
    </div>
  );
}

// Un bouton qui ouvre un menu : le + d'une liste, par exemple.
export function MenuButton({
  items,
  onSelect,
  icon,
  label,
  title,
  tone = 'ghost',
  size = 'sm',
  filter,
  placeholder,
  empty,
  align = 'end',
  width = 280,
  disabled,
  className
}: {
  items: MenuItem[];
  onSelect: (value: string) => void;
  icon?: IconSvgElement;
  label?: ReactNode;
  title?: string;
  tone?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md';
  filter?: boolean;
  placeholder?: string;
  empty?: ReactNode;
  align?: 'start' | 'end';
  width?: number;
  disabled?: boolean;
  className?: string;
}) {
  const anchor = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  return (
    <>
      <Button ref={anchor} tone={tone} size={size} icon={icon} title={title} disabled={disabled} expanded={open} className={className} onClick={() => setOpen(!open)}>
        {label}
      </Button>
      <Popover anchor={anchor} open={open} onClose={close} width={width} align={align}>
        <Menu
          items={items}
          filter={filter}
          placeholder={placeholder}
          empty={empty}
          onSelect={value => {
            setOpen(false);
            onSelect(value);
          }}
        />
      </Popover>
    </>
  );
}
