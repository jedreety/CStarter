// Les listes nommées : les defines et l'environnement du débogueur. Chacune
// est une section, dont le + ouvre une ligne à remplir : Entrée l'ajoute, Échap l'abandonne.

import { useRef, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Cancel01Icon, PlusSignIcon } from '@hugeicons/core-free-icons';
import { t } from '../lib/i18n';
import type { Define } from '../lib/model';
import { Button, Icon, Section, TextField } from './ui';
import './editors.css';

const ROW = {
  layout: true,
  initial: { opacity: 0, height: 0 },
  animate: { opacity: 1, height: 'auto' },
  exit: { opacity: 0, height: 0 },
  transition: { type: 'spring' as const, bounce: 0, duration: 0.3 }
};

function text(value: Define): string {
  if (value === null) return '';
  if (typeof value === 'object') return value.string;
  return String(value);
}

function isString(value: Define): boolean {
  return value !== null && typeof value === 'object';
}

function make(content: string, cString: boolean): Define {
  if (cString) return { string: content };
  return content === '' ? null : content;
}

export function DefinesSection({
  title,
  defines,
  onSet,
  onRemove
}: {
  title: string;
  defines: Record<string, Define>;
  onSet: (name: string, value: Define) => void;
  onRemove: (name: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  return (
    <Section title={title} action={<Button tone="ghost" size="sm" icon={PlusSignIcon} title={t('Ajouter un define', 'Add a define')} onClick={() => setAdding(true)} />}>
      <div className="pairs">
        <AnimatePresence initial={false}>
          {Object.entries(defines).map(([key, current]) => (
            <motion.div key={key} className="pairs__row" {...ROW}>
              <span className="pairs__name mono">{key}</span>
              <span className="pairs__equals">=</span>
              <TextField value={text(current)} placeholder={t('sans valeur', 'no value')} mono onCommit={v => onSet(key, make(v, isString(current)))} />
              <QuoteToggle on={isString(current)} onChange={on => onSet(key, make(text(current), on))} />
              <Remove name={key} onClick={() => onRemove(key)} />
            </motion.div>
          ))}
          {adding ? (
            <NewPair
              key="new"
              placeholder={t('NOM', 'NAME')}
              quote
              onDone={(name, value, quoted) => {
                setAdding(false);
                if (name) onSet(name, make(value, quoted));
              }}
            />
          ) : null}
        </AnimatePresence>
      </div>
    </Section>
  );
}

export function EnvironmentSection({ title, values, onChange }: { title: string; values: Record<string, string>; onChange: (values: Record<string, string>) => void }) {
  const [adding, setAdding] = useState(false);
  return (
    <Section title={title} action={<Button tone="ghost" size="sm" icon={PlusSignIcon} title={t('Ajouter une variable', 'Add a variable')} onClick={() => setAdding(true)} />}>
      <div className="pairs pairs--plain">
        <AnimatePresence initial={false}>
          {Object.entries(values).map(([key, current]) => (
            <motion.div key={key} className="pairs__row" {...ROW}>
              <span className="pairs__name mono">{key}</span>
              <span className="pairs__equals">=</span>
              <TextField value={current} mono onCommit={v => onChange({ ...values, [key]: v })} />
              <Remove
                name={key}
                onClick={() => {
                  const next = { ...values };
                  delete next[key];
                  onChange(next);
                }}
              />
            </motion.div>
          ))}
          {adding ? (
            <NewPair
              key="new"
              placeholder="VARIABLE"
              onDone={(name, value) => {
                setAdding(false);
                if (name) onChange({ ...values, [name]: value });
              }}
            />
          ) : null}
        </AnimatePresence>
      </div>
    </Section>
  );
}

// La ligne qu'ouvre le + : elle s'ajoute par Entrée, ou quand le focus la quitte avec un nom.
function NewPair({ placeholder, quote = false, onDone }: { placeholder: string; quote?: boolean; onDone: (name: string, value: string, quoted: boolean) => void }) {
  const [name, setName] = useState('');
  const [value, setValue] = useState('');
  const [quoted, setQuoted] = useState(false);
  const finished = useRef(false);
  const done = (keep: boolean) => {
    if (finished.current) return;
    finished.current = true;
    onDone(keep ? name.trim() : '', value, quoted);
  };
  return (
    <motion.div
      className="pairs__row pairs__row--new"
      {...ROW}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) done(true);
      }}
      onKeyDown={event => {
        if (event.key === 'Enter') done(true);
        if (event.key === 'Escape') {
          event.stopPropagation();
          done(false);
        }
      }}
    >
      <input className="field field--mono" autoFocus value={name} placeholder={placeholder} spellCheck={false} onChange={e => setName(e.target.value)} />
      <span className="pairs__equals">=</span>
      <input className="field field--mono" value={value} placeholder={quote ? t('sans valeur', 'no value') : undefined} spellCheck={false} onChange={e => setValue(e.target.value)} />
      {quote ? <QuoteToggle on={quoted} onChange={setQuoted} /> : null}
      <span />
    </motion.div>
  );
}

function Remove({ name, onClick }: { name: string; onClick: () => void }): ReactNode {
  return (
    <button className="pairs__remove" aria-label={t(`Retirer ${name}`, `Remove ${name}`)} onClick={onClick}>
      <Icon icon={Cancel01Icon} size={12} stroke={2.2} />
    </button>
  );
}

function QuoteToggle({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button className={`quote${on ? ' quote--on' : ''}`} title={t('Chaîne C', 'C string')} aria-pressed={on} onClick={() => onChange(!on)}>
      “ ”
    </button>
  );
}
