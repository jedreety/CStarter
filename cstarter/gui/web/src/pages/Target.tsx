// Un target (targets/<nom>.json) : ce qu'il est, ses fichiers, ses
// configurations, une à une ou toutes côte à côte, et, pour un exécutable, son débogueur. Ce qu'il
// lie se règle dans la page Dépendances. Tout change en mémoire, jusqu'à l'enregistrement.

import { useEffect, useState, type ReactNode } from 'react';
import { AnimatePresence, motion, type Variants } from 'motion/react';
import { Delete02Icon, PackageIcon, PlayIcon, PlusSignIcon } from '@hugeicons/core-free-icons';
import FuseButton from '../reactbits/FuseButton';
import GlideSelect from '../reactbits/GlideSelect';
import { changeRuntime, edit, exportTarget, navigate, renameTarget, setField } from '../lib/actions';
import { openSheet, SheetFrame } from '../lib/dialogs';
import { t } from '../lib/i18n';
import { cStandards, optimizations, RUNTIMES, STANDARD_LABELS, STANDARDS, subsystems, targetKinds, targetTypes, warningLevels } from '../lib/labels';
import type { Configuration, Project, Target } from '../lib/model';
import { useProject } from '../lib/store';
import { DefinesSection, EnvironmentSection } from '../components/editors';
import { PathField, PathList } from '../components/paths';
import { typeIcon } from '../components/Sidebar';
import { Button, Chip, Icon, Input, PageHeader, Reveal, Row, Section, Segmented, TextField, Toggle, TokenList } from '../components/ui';
import './pages.css';

type Tab = 'general' | 'sources' | 'configurations' | 'debugger';

const TABS: Tab[] = ['general', 'sources', 'configurations', 'debugger'];

// Un onglet arrive du côté où il est dans la barre : de la droite quand on avance, de la gauche sinon.
const SLIDE: Variants = {
  enter: (direction: number) => ({ opacity: 0, x: 14 * direction, filter: 'blur(4px)' }),
  shown: { opacity: 1, x: 0, filter: 'blur(0px)', transition: { type: 'spring', bounce: 0, duration: 0.3 } },
  leave: (direction: number) => ({ opacity: 0, x: -10 * direction, filter: 'blur(3px)', transition: { duration: 0.12, ease: [0.4, 0, 1, 1] } })
};

// Un filtre de la boîte de Windows : pywebview n'accepte que lettres, chiffres et espaces avant la parenthèse.
const SOURCE_FILES = ['Sources (*.cpp;*.cc;*.cxx;*.c)'];
const items = (labels: Record<string, string>) => Object.entries(labels).map(([value, label]) => ({ value, label }));
// La vue de toutes les configurations côte à côte, dans le sélecteur de configuration.
const ALL = '\u0000all';

// L'onglet ouvert reste le même d'un target à l'autre : comparer deux configurations se fait vite.
let lastTab: Tab = 'general';

export default function TargetPage({ name }: { name: string }) {
  const project = useProject();
  const target = project.targets[name];
  const [tab, setTab] = useState<Tab>(lastTab);
  const [direction, setDirection] = useState(1);
  if (!target) return null;
  const executable = target.type === 'executable';
  const startup = project.solution.startup_target === name;
  const shown = !executable && tab === 'debugger' ? 'general' : tab;
  const choose = (next: Tab) => {
    setDirection(TABS.indexOf(next) >= TABS.indexOf(shown) ? 1 : -1);
    lastTab = next;
    setTab(next);
  };
  return (
    <>
      <PageHeader
        title={target.name}
        meta={
          <>
            <Chip tone="accent" icon={typeIcon(target.type)}>
              {targetTypes()[target.type]}
            </Chip>
            {startup ? (
              <Chip tone="success" icon={PlayIcon}>
                {t('Démarrage', 'Startup')}
              </Chip>
            ) : null}
          </>
        }
        actions={
          executable ? (
            startup ? null : (
              <Button icon={PlayIcon} onClick={() => edit('set_startup_target', name)}>
                {t('Définir comme démarrage', 'Set as startup')}
              </Button>
            )
          ) : (
            <Button icon={PackageIcon} onClick={() => exportSheet(project, target)}>
              {t('Exporter vers le cache', 'Export to the cache')}
            </Button>
          )
        }
      />
      <div className="tabs">
        <Segmented
          tabs
          value={shown}
          onChange={choose}
          items={[
            { value: 'general' as Tab, label: t('Général', 'General') },
            { value: 'sources' as Tab, label: 'Sources' },
            { value: 'configurations' as Tab, label: 'Configurations' },
            ...(executable ? [{ value: 'debugger' as Tab, label: t('Débogage', 'Debugging') }] : [])
          ]}
        />
      </div>
      <AnimatePresence mode="popLayout" initial={false} custom={direction}>
        <motion.div key={shown} custom={direction} variants={SLIDE} initial="enter" animate="shown" exit="leave">
          {shown === 'general' ? <General target={target} /> : null}
          {shown === 'sources' ? <Sources target={target} /> : null}
          {shown === 'configurations' ? <Configurations target={target} /> : null}
          {shown === 'debugger' ? <Debugger target={target} /> : null}
        </motion.div>
      </AnimatePresence>
    </>
  );
}

function General({ target }: { target: Target }) {
  const at = (...path: (string | number)[]) => ['targets', target.name, ...path];
  return (
    <>
      <Section>
        <Row label={t('Nom', 'Name')}>
          <TextField value={target.name} onCommit={v => v.trim() && renameTarget(target.name, v.trim())} />
        </Row>
        <Row label="Type">
          <Segmented size="sm" label="Type" value={target.type} onChange={v => setField(at('type'), v)} items={items(targetKinds())} />
        </Row>
        <Reveal when={target.type === 'executable'}>
          <Row label={t('Sous-système', 'Subsystem')}>
            <Segmented size="sm" label={t('Sous-système', 'Subsystem')} value={target.subsystem} onChange={v => setField(at('subsystem'), v)} items={items(subsystems())} />
          </Row>
        </Reveal>
        <Row label={t('Standard C++', 'C++ standard')}>
          <Segmented
            size="sm"
            label={t('Standard C++', 'C++ standard')}
            value={target.standard}
            onChange={v => setField(at('standard'), v)}
            items={STANDARDS.map(s => ({ value: s, label: STANDARD_LABELS[s] }))}
          />
        </Row>
        <Row label={t('Standard C', 'C standard')}>
          <Segmented size="sm" label={t('Standard C', 'C standard')} value={target.c_standard ?? ''} onChange={v => setField(at('c_standard'), v || null)} items={items(cStandards())} />
        </Row>
        <Pch target={target} />
      </Section>
      <div className="danger-zone">
        <FuseButton
          label={t('Supprimer le target', 'Remove the target')}
          undoLabel={t('Annuler', 'Undo')}
          doneLabel={t('Supprimé', 'Removed')}
          icon={<Icon icon={Delete02Icon} size={14} stroke={1.9} />}
          commitOn="fuseEnd"
          undoWindow={2600}
          size="sm"
          radius={9}
          background="rgba(255,107,107,0.12)"
          color="#ff8f8f"
          fuseColor="#ff6b6b"
          onCommit={async () => {
            if (await edit('remove_vcxproj', target.name)) navigate('overview');
          }}
        />
      </div>
    </>
  );
}

// L'en-tête précompilé : son nom, que les sources incluent, et le .cpp qui le crée.
function Pch({ target }: { target: Target }) {
  const [on, setOn] = useState(Boolean(target.pch));
  const [pch, setPch] = useState(target.pch ?? { header: 'pch.h', source: '' });
  useEffect(() => {
    setOn(Boolean(target.pch));
    if (target.pch) setPch(target.pch);
  }, [target.pch]);
  const commit = (next: { header: string; source: string }) => {
    setPch(next);
    if (next.header && next.source) edit('set_pch', target.name, next.header, next.source);
  };
  return (
    <>
      <Row label={t('En-tête précompilé', 'Precompiled header')}>
        <Toggle
          on={on}
          label={t('En-tête précompilé', 'Precompiled header')}
          onChange={value => {
            setOn(value);
            if (!value && target.pch) edit('set_pch', target.name, null);
          }}
        />
      </Row>
      <Reveal when={on}>
        <Row label={t('En-tête', 'Header')}>
          <TextField value={pch.header} mono placeholder="pch.h" width={200} onCommit={v => commit({ ...pch, header: v.trim() })} />
        </Row>
        <Row label="Source">
          <PathField kind="file" types={SOURCE_FILES} value={pch.source} placeholder={`${target.name}/src/pch.cpp`} onCommit={v => commit({ ...pch, source: v })} />
        </Row>
      </Reveal>
    </>
  );
}

function Sources({ target }: { target: Target }) {
  const at = (...path: string[]) => ['targets', target.name, ...path];
  const sources = target.sources;
  return (
    <>
      <Section
        title={t('Fichiers', 'Files')}
        action={
          <Segmented
            size="sm"
            label={t('Fichiers', 'Files')}
            value={sources.mode}
            onChange={v => setField(at('sources', 'mode'), v)}
            items={[
              { value: 'auto', label: t('Dossiers', 'Folders') },
              { value: 'manual', label: t('Motifs', 'Patterns') }
            ]}
          />
        }
      >
        {sources.mode === 'auto' ? (
          <Row label={t('Dossiers', 'Folders')} align="start">
            <PathList values={sources.dirs} onChange={v => edit('set_source_dirs', target.name, v)} />
          </Row>
        ) : (
          <Row label={t('Motifs', 'Patterns')} align="start">
            <PathList values={sources.files} kinds={['file']} typed placeholder={`${target.name}/src/**/*.cpp`} onChange={v => setField(at('sources', 'files'), v)} />
          </Row>
        )}
        <Row label="Exclusions" align="start">
          <PathList
            values={sources.exclude}
            kinds={['folder', 'file']}
            typed
            placeholder="**/tests/**"
            adapt={(path, kind) => (kind === 'folder' ? `${path}/**` : path)}
            onChange={v => setField(at('sources', 'exclude'), v)}
          />
        </Row>
        <Row label="Include" align="start">
          <PathList values={sources.include_dirs} onChange={v => setField(at('sources', 'include_dirs'), v)} />
        </Row>
      </Section>
      <Section title={t('Emplacements', 'Locations')}>
        {target.type !== 'executable' ? (
          <Row label={t('Headers publics', 'Public headers')}>
            <PathField value={target.public_headers ?? ''} placeholder={t('Aucun', 'None')} onCommit={v => edit('set_public_headers', target.name, v || null)} />
          </Row>
        ) : null}
        <Row label={t('Projet .vcxproj', '.vcxproj project')}>
          <PathField value={target.vcxproj_dir} onCommit={v => edit('set_vcxproj_dir', target.name, v)} />
        </Row>
        <Row label={t('Binaires', 'Binaries')}>
          <PathField value={target.output.bin_dir} onCommit={v => setField(at('output', 'bin_dir'), v)} />
        </Row>
        <Row label={t('Intermédiaires', 'Intermediates')}>
          <PathField value={target.output.obj_dir} onCommit={v => setField(at('output', 'obj_dir'), v)} />
        </Row>
      </Section>
    </>
  );
}

function Configurations({ target }: { target: Target }) {
  const [selected, setSelected] = useState(target.configurations[0]?.name);
  const all = selected === ALL && target.configurations.length > 1;
  const current = target.configurations.find(c => c.name === selected) ?? target.configurations[0];
  if (!current) return null;
  const index = target.configurations.indexOf(current);
  const at = (...path: (string | number)[]) => ['targets', target.name, 'configurations', index, ...path];

  const addConfiguration = async () => {
    const result = await openSheet<{ name: string; copyOf: string }>(close => <NewConfiguration target={target} close={close} />, 440);
    if (result && (await edit('add_configuration', target.name, result.name, result.copyOf))) setSelected(result.name);
  };
  const rename = async (name: string) => {
    if (name && name !== current.name && (await edit('rename_configuration', target.name, current.name, name))) setSelected(name);
  };

  return (
    <>
      <div className="config-bar">
        <Segmented
          label="Configuration"
          value={all ? ALL : current.name}
          onChange={setSelected}
          items={[
            ...(target.configurations.length > 1 ? [{ value: ALL, label: t('Toutes', 'All') }] : []),
            ...target.configurations.map(c => ({ value: c.name, label: c.name }))
          ]}
        />
        <Button tone="ghost" size="sm" icon={PlusSignIcon} title={t('Nouvelle configuration', 'New configuration')} onClick={addConfiguration} />
      </div>

      {/* Une autre configuration se fond à la place de la précédente */}
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.div
          key={all ? ALL : current.name}
          initial={{ opacity: 0, filter: 'blur(3px)' }}
          animate={{ opacity: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, transition: { duration: 0.1 } }}
          transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
        >
          {all ? (
            <ConfigurationGrid target={target} onOpen={setSelected} />
          ) : (
            <>
              <Section>
                <Row label={t('Nom', 'Name')}>
                  <TextField key={current.name} value={current.name} onCommit={v => rename(v.trim())} />
                </Row>
              </Section>

              <Section title={t('Compilation', 'Build settings')}>
                <Row label={t('Optimisation', 'Optimization')}>
                  <Segmented size="sm" label={t('Optimisation', 'Optimization')} value={current.optimization} onChange={v => setField(at('optimization'), v)} items={items(optimizations())} />
                </Row>
                <Row label={t('Avertissements', 'Warnings')}>
                  <Segmented size="sm" label={t('Avertissements', 'Warnings')} value={current.warning_level} onChange={v => setField(at('warning_level'), v)} items={items(warningLevels())} />
                </Row>
                <Row label="Runtime">
                  <Segmented size="sm" label="Runtime" value={current.runtime_library} onChange={v => changeRuntime(target.name, index, v)} items={items(RUNTIMES)} />
                </Row>
                {switches().map(([field, label]) => (
                  <Row key={field} label={label}>
                    <Toggle on={current[field]} onChange={v => setField(at(field), v)} label={label} />
                  </Row>
                ))}
              </Section>

              <DefinesSection
                title="Defines"
                defines={current.defines}
                onSet={(define, value) => edit('add_config_define', target.name, current.name, define, value)}
                onRemove={define => edit('remove_config_define', target.name, current.name, define)}
              />

              <Section title="Options">
                <Row label={t('Compilateur', 'Compiler')} align="start">
                  <TokenList values={current.compiler_options} placeholder="/utf-8" onChange={v => setField(at('compiler_options'), v)} />
                </Row>
                <Row label={t('Éditeur de liens', 'Linker')} align="start">
                  <TokenList values={current.linker_options} onChange={v => setField(at('linker_options'), v)} />
                </Row>
              </Section>

              {target.configurations.length > 1 ? (
                <div className="danger-zone">
                  <FuseButton
                    key={current.name}
                    label={t(`Supprimer ${current.name}`, `Remove ${current.name}`)}
                    undoLabel={t('Annuler', 'Undo')}
                    doneLabel={t('Supprimée', 'Removed')}
                    icon={<Icon icon={Delete02Icon} size={14} stroke={1.9} />}
                    commitOn="fuseEnd"
                    undoWindow={2400}
                    size="sm"
                    radius={9}
                    background="rgba(255,107,107,0.12)"
                    color="#ff8f8f"
                    fuseColor="#ff6b6b"
                    onCommit={async () => {
                      if (await edit('remove_configuration', target.name, current.name)) setSelected(target.configurations[0].name);
                    }}
                  />
                </div>
              ) : null}
            </>
          )}
        </motion.div>
      </AnimatePresence>
    </>
  );
}

type Switch = 'debug_info' | 'whole_program_opt' | 'function_level_linking' | 'link_time_code_gen';

// Les réglages oui ou non d'une configuration, et leur nom.
const switches = (): [Switch, string][] => [
  ['debug_info', t('Informations de débogage', 'Debugging information')],
  ['whole_program_opt', t('Optimisation du programme entier', 'Whole program optimization')],
  ['function_level_linking', t('Liaison au niveau fonction', 'Function-level linking')],
  ['link_time_code_gen', t('Génération de code au link', 'Link-time code generation')]
];

// Toutes les configurations côte à côte : une colonne chacune, les réglages de compilation modifiables
// sur place, les defines et les options résumés ; un nom de colonne ouvre sa configuration.
function ConfigurationGrid({ target, onOpen }: { target: Target; onOpen: (name: string) => void }) {
  const at = (index: number, field: string) => ['targets', target.name, 'configurations', index, field];
  const select = (label: string, value: string, options: Record<string, string>, onChange: (value: string) => void) => (
    <GlideSelect
      value={value}
      onChange={onChange}
      options={Object.entries(options).map(([key, text]) => ({ value: key, label: text }))}
      size="sm"
      menuWidth={170}
      surfaceColor="rgba(255,255,255,0.055)"
      highlightColor="#2a2a31"
      ariaLabel={label}
    />
  );
  const text = (values: string[]) => (values.length ? <span className="mono ellipsis selectable">{values.join(' ')}</span> : <span className="faint">—</span>);
  const defines = (c: Configuration) => Object.entries(c.defines).map(([name, value]) => (value === null ? name : `${name}=${typeof value === 'object' ? `"${value.string}"` : value}`));
  const rows: [string, (c: Configuration, index: number) => ReactNode][] = [
    [t('Optimisation', 'Optimization'), (c, i) => select(t('Optimisation', 'Optimization'), c.optimization, optimizations(), v => setField(at(i, 'optimization'), v))],
    [t('Avertissements', 'Warnings'), (c, i) => select(t('Avertissements', 'Warnings'), c.warning_level, warningLevels(), v => setField(at(i, 'warning_level'), v))],
    ['Runtime', (c, i) => select('Runtime', c.runtime_library, RUNTIMES, v => changeRuntime(target.name, i, v))],
    ...switches().map(([field, label]): [string, (c: Configuration, index: number) => ReactNode] => [
      label,
      (c, i) => <Toggle on={c[field]} onChange={v => setField(at(i, field), v)} label={`${label} · ${c.name}`} />
    ]),
    ['Defines', c => text(defines(c))],
    [t('Compilateur', 'Compiler'), c => text(c.compiler_options)],
    [t('Éditeur de liens', 'Linker'), c => text(c.linker_options)]
  ];
  return (
    <Section title={t('Compilation', 'Build settings')}>
      <div className="config-grid" style={{ gridTemplateColumns: `210px repeat(${target.configurations.length}, minmax(150px, 1fr))` }}>
        <span />
        {target.configurations.map(c => (
          <button key={c.name} type="button" className="config-grid__head" onClick={() => onOpen(c.name)}>
            {c.name}
          </button>
        ))}
        {rows.map(([label, cell]) => (
          <div key={label} className="config-grid__row">
            <span className="config-grid__label">{label}</span>
            {target.configurations.map((c, i) => (
              <span key={c.name} className="config-grid__cell">
                {cell(c, i)}
              </span>
            ))}
          </div>
        ))}
      </div>
    </Section>
  );
}

function NewConfiguration({ target, close }: { target: Target; close: (value?: { name: string; copyOf: string }) => void }) {
  const [name, setName] = useState('');
  const [copyOf, setCopyOf] = useState(target.configurations[0].name);
  const create = () => name.trim() && close({ name: name.trim(), copyOf });
  return (
    <SheetFrame
      title={t('Nouvelle configuration', 'New configuration')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close()}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={create} disabled={!name.trim()}>
            {t('Ajouter', 'Add')}
          </Button>
        </>
      }
    >
      <div className="sheet__form">
        <div className="sheet__field">
          <label>{t('Nom', 'Name')}</label>
          <Input value={name} onChange={setName} autoFocus onEnter={create} />
        </div>
        <div className="sheet__field">
          <label>{t('Copie de', 'Copy of')}</label>
          <Segmented label={t('Copie de', 'Copy of')} value={copyOf} onChange={setCopyOf} items={target.configurations.map(c => ({ value: c.name, label: c.name }))} />
        </div>
      </div>
    </SheetFrame>
  );
}

function Debugger({ target }: { target: Target }) {
  const at = (...path: string[]) => ['targets', target.name, 'debugger', ...path];
  return (
    <>
      <Section>
        <Row label={t('Dossier de travail', 'Working folder')}>
          <PathField value={target.debugger.working_dir} onCommit={v => setField(at('working_dir'), v || '.')} />
        </Row>
        <Row label="Arguments">
          <TextField value={target.debugger.arguments} mono onCommit={v => setField(at('arguments'), v)} />
        </Row>
      </Section>
      <EnvironmentSection title={t('Environnement', 'Environment')} values={target.debugger.environment} onChange={v => setField(at('environment'), v)} />
    </>
  );
}

async function exportSheet(project: Project, target: Target): Promise<void> {
  const result = await openSheet<{ configuration: string; name: string; version: string }>(
    close => <ExportSheet project={project} target={target} close={close} />,
    480
  );
  if (result) exportTarget(target.name, result.configuration, result.name, result.version);
}

function ExportSheet({ project, target, close }: { project: Project; target: Target; close: (value?: { configuration: string; name: string; version: string }) => void }) {
  const [configuration, setConfiguration] = useState(target.configurations.find(c => c.name === 'Release')?.name ?? target.configurations[0].name);
  const runtime = target.configurations.find(c => c.name === configuration)?.runtime_library ?? '';
  const [name, setName] = useState(`${target.name.toLowerCase()}_${runtime.toLowerCase()}`);
  const [version, setVersion] = useState(project.version);
  return (
    <SheetFrame
      title={t('Exporter vers le cache', 'Export to the cache')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close()}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={() => close({ configuration, name, version })} disabled={!name.trim() || !version.trim()}>
            {t('Exporter', 'Export')}
          </Button>
        </>
      }
    >
      <div className="sheet__form">
        <div className="sheet__field">
          <label>Configuration</label>
          <Segmented
            label="Configuration"
            value={configuration}
            onChange={v => {
              setConfiguration(v);
              const rt = target.configurations.find(c => c.name === v)?.runtime_library ?? '';
              setName(`${target.name.toLowerCase()}_${rt.toLowerCase()}`);
            }}
            items={target.configurations.map(c => ({ value: c.name, label: c.name }))}
          />
        </div>
        <div className="sheet__grid">
          <div className="sheet__field">
            <label>{t('Nom de l’entrée', 'Entry name')}</label>
            <Input value={name} onChange={setName} mono />
          </div>
          <div className="sheet__field">
            <label>Version</label>
            <Input value={version} onChange={setVersion} mono />
          </div>
        </div>
      </div>
    </SheetFrame>
  );
}
