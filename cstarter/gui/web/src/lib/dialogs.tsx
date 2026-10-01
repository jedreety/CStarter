// Les feuilles : une question à la fois, posée au-dessus de la fenêtre, qui se ferme par Échap.

import { useState, type ReactNode } from 'react';
import { Download04Icon, PackageIcon, PlusSignIcon } from '@hugeicons/core-free-icons';
import GlideSelect from '../reactbits/GlideSelect';
import StatusMark from '../reactbits/StatusMark';
import { guessFolder, SourceFolder } from '../components/paths';
import { MenuButton } from '../components/Popover';
import { Button, Row, Toggle, TokenList } from '../components/ui';
import { t } from './i18n';
import { builders, statusWords } from './labels';
import type { AnalysisReport, CMakeOption } from './model';
import { packages } from './packages';
import { getState, setState, useStore } from './store';

let sheetCounter = 0;

export function openSheet<T>(render: (close: (value?: T) => void) => ReactNode, width = 480): Promise<T | undefined> {
  return new Promise(resolve => {
    const id = ++sheetCounter;
    const close = (value?: unknown) => {
      setState(s => ({ sheets: s.sheets.filter(sheet => sheet.id !== id) }));
      resolve(value as T | undefined);
    };
    setState(s => ({ sheets: [...s.sheets, { id, width, resolve: close, render: done => render(done as (value?: T) => void) }] }));
  });
}

export function SheetFrame({ title, children, actions }: { title: ReactNode; children?: ReactNode; actions: ReactNode }) {
  return (
    <>
      <h2 className="sheet__title">{title}</h2>
      {children ? <div className="sheet__body">{children}</div> : null}
      <footer className="sheet__actions">{actions}</footer>
    </>
  );
}

export function confirmOverwrite(paths: string[]): Promise<boolean | undefined> {
  return openSheet<boolean>(close => (
    <SheetFrame
      title={t('Écraser ces fichiers ?', 'Overwrite these files?')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close(false)}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={() => close(true)}>
            {t('Écraser', 'Overwrite')}
          </Button>
        </>
      }
    >
      <ul className="sheet__paths mono">
        {paths.map(path => (
          <li key={path}>{path}</li>
        ))}
      </ul>
    </SheetFrame>
  ));
}

export function askUnsaved(): Promise<'save' | 'discard' | 'cancel' | undefined> {
  return openSheet<'save' | 'discard' | 'cancel'>(close => (
    <SheetFrame
      title={t('Enregistrer les modifications ?', 'Save the changes?')}
      actions={
        <>
          <Button tone="danger" onClick={() => close('discard')} className="sheet__left">
            {t('Ne pas enregistrer', 'Don’t save')}
          </Button>
          <Button tone="ghost" onClick={() => close('cancel')}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={() => close('save')}>
            {t('Enregistrer', 'Save')}
          </Button>
        </>
      }
    />
  ));
}

// Les prérequis : chaque outil, présent ou à installer par winget.
export function openPrerequisites(install: (name: string) => Promise<boolean>): Promise<void | undefined> {
  return openSheet<void>(close => <Prerequisites install={install} close={close} />, 440);
}

function Prerequisites({ install, close }: { install: (name: string) => Promise<boolean>; close: () => void }) {
  const list = useStore(s => s.prerequisites) ?? [];
  const busy = useStore(s => s.busy);
  const [installing, setInstalling] = useState<string | null>(null);
  const run = async (name: string) => {
    setInstalling(name);
    await install(name);
    setInstalling(null);
  };
  return (
    <SheetFrame
      title={t('Outils', 'Tools')}
      actions={
        <Button tone="ghost" onClick={() => close()}>
          {t('Fermer', 'Close')}
        </Button>
      }
    >
      <div className="prerequisites">
        {list.map(tool => (
          <div key={tool.name} className="prerequisites__row">
            <StatusMark
              status={installing === tool.name ? 'running' : tool.present ? 'done' : 'pending'}
              label={tool.name}
              size={18}
              fontSize={13.5}
              strike={false}
              color="var(--text)"
              doneColor="var(--success)"
              errorColor="var(--danger)"
              spoken={statusWords()}
            />
            {tool.present ? null : (
              <Button tone="secondary" size="sm" onClick={() => run(tool.name)} disabled={busy}>
                {t('Installer', 'Install')}
              </Button>
            )}
          </div>
        ))}
      </div>
    </SheetFrame>
  );
}

// Les paramètres d'une dépendance téléchargée : le builder détecté ; pour
// CMake, ceux de son cache, chacun avec son aide, et seuls les paramètres changés deviennent des
// options ; pour les builders manual et none, les dossiers de la source, choisis dans son arbre et
// devinés d'avance. Et les bibliothèques du cache qu'elle attend.

export interface BuildChoice {
  system: string;
  flags: string[];
  requires: string[];
}

export function chooseBuild(name: string, version: string, report: AnalysisReport): Promise<BuildChoice | undefined> {
  return openSheet<BuildChoice>(close => <ParameterSheet name={name} version={version} report={report} close={close} />, 660);
}

function ParameterSheet({ name, version, report, close }: { name: string; version: string; report: AnalysisReport; close: (value?: BuildChoice) => void }) {
  const platforms = getState().view?.project?.solution.platforms ?? ['x64'];
  const cached = packages(useStore(s => s.cache) ?? []);
  const folders = report.folders ?? {};
  const [system, setSystem] = useState(report.suggested_system);
  const [values, setValues] = useState<Record<string, string>>({});
  const [extra, setExtra] = useState<string[]>([]);
  const [requires, setRequires] = useState<string[]>([]);
  const [filter, setFilter] = useState('');
  const [designated, setDesignated] = useState<Record<string, string | null>>(() => {
    const guess: Record<string, string | null> = { include: guessFolder(folders, 'headers') };
    for (const platform of platforms) {
      guess[`lib/${platform}`] = guessFolder(folders, 'lib', platform);
      guess[`bin/${platform}`] = guessFolder(folders, 'dll', platform);
    }
    return guess;
  });
  const designate = (key: string) => (value: string | null) => setDesignated(current => ({ ...current, [key]: value }));

  const cmake = system === 'cmake';
  const manual = system === 'manual';
  const headers = system === 'none';
  const options = [...report.cmake_options].sort((a, b) => Number(b.type === 'BOOL') - Number(a.type === 'BOOL') || a.name.localeCompare(b.name));
  const shown = options.filter(option => `${option.name} ${option.description}`.toLowerCase().includes(filter.trim().toLowerCase()));
  const changed = (option: CMakeOption) => values[option.name] !== undefined && values[option.name] !== option.default;
  const offered = [...new Set(cached.map(pkg => pkg.name))].filter(pkg => pkg !== name && !requires.includes(pkg));

  // Les dossiers deviennent des options du builder : include=, lib/<plateforme>=, bin/<plateforme>=.
  const keys = manual ? ['include', ...platforms.flatMap(p => [`lib/${p}`, `bin/${p}`])] : headers && designated.include !== 'include' ? ['include'] : [];
  const flags = cmake ? options.filter(changed).map(option => `-D${option.name}=${values[option.name]}`) : manual || headers ? keys.filter(key => designated[key]).map(key => `${key}=${designated[key]}`) : extra;
  const ready = manual ? platforms.every(p => designated[`lib/${p}`]) : headers ? Boolean(designated.include) : true;

  return (
    <SheetFrame
      title={
        <span className="params__title">
          {name}
          <span className="params__version">{version}</span>
        </span>
      }
      actions={
        <>
          <Button tone="ghost" onClick={() => close()}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" icon={Download04Icon} onClick={() => close({ system, flags, requires })} disabled={!ready}>
            {t('Installer', 'Install')}
          </Button>
        </>
      }
    >
      <div className="params">
        <div className="params__head">
          <GlideSelect
            value={system}
            onChange={setSystem}
            options={Object.entries(builders()).map(([value, label]) => ({ value, label, tag: value === report.suggested_system ? t('détecté', 'detected') : undefined }))}
            menuWidth={240}
            surfaceColor="#1d1d22"
            highlightColor="#2c2c33"
            ariaLabel={t('Système de build', 'Build system')}
          />
          {cmake && options.length > 8 ? (
            <input
              className="field field--boxed params__filter"
              value={filter}
              placeholder={t('Rechercher', 'Search')}
              spellCheck={false}
              onChange={event => setFilter(event.target.value)}
            />
          ) : null}
        </div>
        {cmake ? (
          <div className="params__list">
            {shown.map(option => (
              <Parameter
                key={option.name}
                option={option}
                value={values[option.name] ?? option.default}
                changed={changed(option)}
                onChange={value => setValues(current => ({ ...current, [option.name]: value }))}
              />
            ))}
          </div>
        ) : manual || headers ? (
          <div className="params__folders">
            <Row label="Headers">
              <SourceFolder folders={folders} root={name} want="headers" value={designated.include} onChange={designate('include')} optional={manual} />
            </Row>
            {manual
              ? platforms.map(platform => (
                  <div key={platform} className="params__platform">
                    <Row label={t(`Bibliothèques ${platform}`, `Libraries ${platform}`)}>
                      <SourceFolder folders={folders} root={name} want="lib" value={designated[`lib/${platform}`]} onChange={designate(`lib/${platform}`)} />
                    </Row>
                    <Row label={`DLL ${platform}`}>
                      <SourceFolder folders={folders} root={name} want="dll" value={designated[`bin/${platform}`]} onChange={designate(`bin/${platform}`)} optional />
                    </Row>
                  </div>
                ))
              : null}
          </div>
        ) : (
          <div className="sheet__field params__extra">
            <label>Options</label>
            <TokenList values={extra} onChange={setExtra} />
          </div>
        )}
        {cached.length ? (
          <Row label={t('Attend', 'Requires')}>
            <TokenList
              values={requires}
              onChange={setRequires}
              typed={false}
              extra={
                offered.length ? (
                  <MenuButton
                    icon={PlusSignIcon}
                    title={t('Ajouter une bibliothèque attendue', 'Add a required library')}
                    align="start"
                    width={240}
                    filter={offered.length > 8}
                    items={offered.map(pkg => ({ value: pkg, label: pkg, icon: PackageIcon }))}
                    onSelect={pkg => setRequires([...requires, pkg])}
                  />
                ) : null
              }
            />
          </Row>
        ) : null}
        {report.notes.length && !manual && !headers ? (
          <ul className="params__notes">
            {report.notes.map(note => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </SheetFrame>
  );
}

function Parameter({ option, value, changed, onChange }: { option: CMakeOption; value: string; changed: boolean; onChange: (value: string) => void }) {
  return (
    <div className={`param${changed ? ' param--changed' : ''}`}>
      <div className="param__text">
        <span className="param__name">{option.name}</span>
        {option.description ? <span className="param__description">{option.description}</span> : null}
      </div>
      <div className="param__control">
        {option.type === 'BOOL' ? (
          <Toggle on={value === 'ON'} onChange={on => onChange(on ? 'ON' : 'OFF')} label={option.name} />
        ) : option.values.length ? (
          <GlideSelect
            value={value}
            onChange={onChange}
            options={option.values.map(item => ({ value: item, label: item }))}
            menuWidth={200}
            align="right"
            size="sm"
            surfaceColor="#1d1d22"
            highlightColor="#2c2c33"
            ariaLabel={option.name}
          />
        ) : (
          <input className="field field--boxed field--mono param__input" value={value} spellCheck={false} onChange={event => onChange(event.target.value)} />
        )}
      </div>
    </div>
  );
}
