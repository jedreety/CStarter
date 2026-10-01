// Les briques de l'interface : boutons, champs, interrupteurs, contrôle segmenté, listes de jetons,
// rangées de réglages. Aucune carte : des rangées séparées par un filet, des sections par l'espace.
// Ce qui s'ouvre depuis un bouton est dans Popover.tsx, les chemins dans paths.tsx.

import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode, type Ref } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react';
import { Cancel01Icon } from '@hugeicons/core-free-icons';
import { t } from '../lib/i18n';
import './ui.css';

const SPRING = { type: 'spring' as const, bounce: 0, duration: 0.35 };

export function Icon({ icon, size = 16, stroke = 1.7, className }: { icon: IconSvgElement; size?: number; stroke?: number; className?: string }) {
  return <HugeiconsIcon icon={icon} size={size} strokeWidth={stroke} className={className} />;
}

type ButtonTone = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent';

export function Button({
  children,
  tone = 'secondary',
  icon,
  size = 'md',
  disabled,
  onClick,
  title,
  className = '',
  type = 'button',
  ref,
  expanded
}: {
  children?: ReactNode;
  tone?: ButtonTone;
  icon?: IconSvgElement;
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  onClick?: () => void;
  title?: string;
  className?: string;
  type?: 'button' | 'submit';
  ref?: Ref<HTMLButtonElement>;
  expanded?: boolean;
}) {
  return (
    <button
      ref={ref}
      type={type}
      className={`btn btn--${tone} btn--${size}${children ? '' : ' btn--icon'} ${className}`}
      disabled={disabled}
      onClick={onClick}
      title={title}
      aria-label={children ? undefined : title}
      aria-expanded={expanded}
    >
      {icon ? <Icon icon={icon} size={size === 'sm' ? 14 : 15} stroke={1.9} /> : null}
      {children ? <span>{children}</span> : null}
    </button>
  );
}

export function TextField({
  value,
  onCommit,
  placeholder,
  mono,
  width,
  autoFocus,
  disabled,
  className = ''
}: {
  value: string;
  onCommit: (value: string) => void;
  placeholder?: string;
  mono?: boolean;
  width?: number | string;
  autoFocus?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const [draft, setDraft] = useState(value);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => setDraft(value), [value]);
  const commit = () => {
    if (draft !== value) onCommit(draft);
  };
  return (
    <input
      ref={ref}
      className={`field${mono ? ' field--mono' : ''} ${className}`}
      style={width !== undefined ? { width } : undefined}
      value={draft}
      placeholder={placeholder}
      autoFocus={autoFocus}
      disabled={disabled}
      spellCheck={false}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => {
        if (e.key === 'Enter') ref.current?.blur();
        if (e.key === 'Escape') {
          setDraft(value);
          requestAnimationFrame(() => ref.current?.blur());
        }
      }}
    />
  );
}

// Un champ contrôlé, pour les formulaires des feuilles : la valeur suit la frappe.
export function Input({
  value,
  onChange,
  placeholder,
  mono,
  autoFocus,
  onEnter,
  invalid
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  mono?: boolean;
  autoFocus?: boolean;
  onEnter?: () => void;
  invalid?: boolean;
}) {
  return (
    <input
      className={`field field--boxed${mono ? ' field--mono' : ''}${invalid ? ' field--invalid' : ''}`}
      aria-invalid={invalid}
      value={value}
      placeholder={placeholder}
      autoFocus={autoFocus}
      spellCheck={false}
      onChange={e => onChange(e.target.value)}
      onKeyDown={e => {
        if (e.key === 'Enter') onEnter?.();
      }}
    />
  );
}

export function Toggle({ on, onChange, disabled, label }: { on: boolean; onChange: (on: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={`toggle${on ? ' toggle--on' : ''}`}
      disabled={disabled}
      onClick={() => onChange(!on)}
    >
      <motion.span className="toggle__knob" layout transition={SPRING} />
    </button>
  );
}

// Un choix parmi quelques valeurs, ou, avec tabs, des onglets : les lecteurs d'écran l'annoncent
// comme l'un ou l'autre.
export function Segmented<T extends string>({
  items,
  value,
  onChange,
  size = 'md',
  tabs = false,
  label
}: {
  items: { value: T; label: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
  size?: 'sm' | 'md';
  tabs?: boolean;
  label?: string;
}) {
  const id = useId();
  return (
    <div className={`segmented segmented--${size}`} role={tabs ? 'tablist' : 'radiogroup'} aria-label={label}>
      {items.map(item => (
        <button
          key={item.value}
          type="button"
          role={tabs ? 'tab' : 'radio'}
          aria-selected={tabs ? item.value === value : undefined}
          aria-checked={tabs ? undefined : item.value === value}
          className={`segmented__item${item.value === value ? ' segmented__item--on' : ''}`}
          onClick={() => onChange(item.value)}
        >
          {item.value === value ? <motion.span layoutId={`segment-${id}`} className="segmented__pill" transition={SPRING} /> : null}
          <span className="segmented__label">{item.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Section({ title, action, children, style }: { title?: ReactNode; action?: ReactNode; children: ReactNode; style?: CSSProperties }) {
  return (
    <section className="section" style={style}>
      {title || action ? (
        <header className="section__head">
          {title ? <h2 className="section__title">{title}</h2> : <span />}
          {action}
        </header>
      ) : null}
      <div className="section__body">{children}</div>
    </section>
  );
}

export function Row({ label, children, align = 'center', mono }: { label: ReactNode; children: ReactNode; align?: 'center' | 'start'; mono?: boolean }) {
  return (
    <div className={`row row--${align}`}>
      <div className={`row__label${mono ? ' mono' : ''}`}>{label}</div>
      <div className="row__control">{children}</div>
    </div>
  );
}

// Une liste de valeurs : chacune se retire, et le champ en ajoute une par Entrée. typed à faux, seul
// extra en ajoute : un sélecteur de dossiers, par exemple.
export function TokenList({
  values,
  onChange,
  placeholder,
  mono = true,
  typed = true,
  extra
}: {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  mono?: boolean;
  typed?: boolean;
  extra?: ReactNode;
}) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const value = draft.trim();
    if (value && !values.includes(value)) onChange([...values, value]);
    setDraft('');
  };
  return (
    <div className="tokens">
      <AnimatePresence initial={false}>
        {values.map(value => (
          <motion.span
            key={value}
            layout
            className={`token${mono ? ' mono' : ''}`}
            initial={{ opacity: 0, scale: 0.9, filter: 'blur(4px)' }}
            animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
            exit={{ opacity: 0, scale: 0.9, filter: 'blur(4px)' }}
            transition={SPRING}
          >
            {value}
            <button type="button" className="token__remove" aria-label={t(`Retirer ${value}`, `Remove ${value}`)} onClick={() => onChange(values.filter(v => v !== value))}>
              <Icon icon={Cancel01Icon} size={11} stroke={2.4} />
            </button>
          </motion.span>
        ))}
      </AnimatePresence>
      {extra}
      {typed ? (
        <input
          className={`tokens__input${mono ? ' mono' : ''}`}
          value={draft}
          placeholder={placeholder ?? t('Ajouter', 'Add')}
          spellCheck={false}
          onChange={e => setDraft(e.target.value)}
          onBlur={add}
          onKeyDown={e => {
            if (e.key === 'Enter') add();
            if (e.key === 'Backspace' && !draft && values.length) onChange(values.slice(0, -1));
          }}
        />
      ) : null}
    </div>
  );
}

// Ce qui apparaît et disparaît dans le flux : la hauteur suit, sans saut.
export function Reveal({ when, children }: { when: boolean; children: ReactNode }) {
  return (
    <AnimatePresence initial={false}>
      {when ? (
        <motion.div
          className="reveal"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ type: 'spring', bounce: 0, duration: 0.34 }}
        >
          {children}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

export function Chip({ children, tone = 'neutral', icon }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'success' | 'danger' | 'warning'; icon?: IconSvgElement }) {
  return (
    <span className={`chip chip--${tone}`}>
      {icon ? <Icon icon={icon} size={12} stroke={2} /> : null}
      {children}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

export function Empty({ icon, title, children }: { icon: IconSvgElement; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty__icon">
        <Icon icon={icon} size={22} stroke={1.5} />
      </span>
      <div className="empty__title">{title}</div>
      {children ? <div className="empty__actions">{children}</div> : null}
    </div>
  );
}

export function PageHeader({ title, meta, actions }: { title: ReactNode; meta?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div className="page-head__text">
        <h1 className="page-head__title">{title}</h1>
        {meta ? <div className="page-head__meta">{meta}</div> : null}
      </div>
      {actions ? <div className="page-head__actions">{actions}</div> : null}
    </header>
  );
}
