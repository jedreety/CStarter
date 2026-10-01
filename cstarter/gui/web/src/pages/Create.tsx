// Créer un projet : neuf, avec un premier target et ses sources de départ,
// ou en copie d'un projet modèle. Le projet prend un dossier à son nom dans l'emplacement choisi.

import { useState } from 'react';
import { motion } from 'motion/react';
import { AppWindowIcon, ArrowLeft01Icon, CommandLineIcon, Folder01Icon, LibraryIcon, Plug01Icon } from '@hugeicons/core-free-icons';
import type { IconSvgElement } from '@hugeicons/react';
import { createFromTemplate, createStarter, peekProject, pickFolder, toast } from '../lib/actions';
import { t } from '../lib/i18n';
import { targetOrder, type Project } from '../lib/model';
import { setState, useStore } from '../lib/store';
import { typeIcon } from '../components/Sidebar';
import { Button, Chip, Icon, Input, PageHeader, Reveal, Row, Section, Segmented } from '../components/ui';
import '../flows/flows.css';
import './Create.css';

// Un nom de projet, qui est aussi celui de son dossier et de son premier target (config.NAME).
const NAME = /^[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?$/;

// Le nom court tient sous l'icône ; le survol dit ce qui sera créé.
interface Start {
  value: string;
  label: string;
  title: string;
  icon: IconSvgElement;
  type: string;
  subsystem: string;
}

const starts = (): Start[] => [
  { value: 'console', label: 'Console', title: t('Programme console', 'Console program'), icon: CommandLineIcon, type: 'executable', subsystem: 'console' },
  { value: 'windows', label: t('Fenêtrée', 'Windowed'), title: t('Programme fenêtré', 'Windowed program'), icon: AppWindowIcon, type: 'executable', subsystem: 'windows' },
  { value: 'static', label: t('Statique', 'Static'), title: t('Bibliothèque statique, .lib', 'Static library, .lib'), icon: LibraryIcon, type: 'static_lib', subsystem: 'console' },
  { value: 'dynamic', label: t('Dynamique', 'Dynamic'), title: t('Bibliothèque dynamique, .dll', 'Dynamic library, .dll'), icon: Plug01Icon, type: 'dynamic_lib', subsystem: 'console' }
];

// Ce qu'écrit un départ, relatif au dossier du projet : .cstarter/ et les sources de create_starter.
const starterFiles = (start: Start, name: string): string[] =>
  start.type === 'executable' ? ['.cstarter\\', `${name}\\src\\main.cpp`] : ['.cstarter\\', `${name}\\include\\${name}.h`, `${name}\\src\\${name}.cpp`];

const parentOf = (path?: string) => (path ? path.replace(/[\\/]+$/, '').replace(/[\\/][^\\/]*$/, '') : '');

export default function Create() {
  const recent = useStore(s => s.recent);
  const busy = useStore(s => s.busy);
  const [mode, setMode] = useState<'starter' | 'template'>('starter');
  const [name, setName] = useState('');
  const [location, setLocation] = useState(() => parentOf(recent[0]?.path));
  const [start, setStart] = useState('console');
  const [template, setTemplate] = useState<Project | null>(null);
  const chosen = starts().find(s => s.value === start)!;
  const trimmed = name.trim();
  const valid = NAME.test(trimmed);
  const folder = location && trimmed ? `${location.replace(/[\\/]+$/, '')}\\${trimmed}` : location;
  const ready = valid && Boolean(location) && (mode === 'starter' || Boolean(template)) && !busy;

  const chooseLocation = async () => {
    const picked = await pickFolder();
    if (picked) setLocation(picked);
  };
  const chooseTemplate = async () => {
    const picked = await pickFolder();
    if (!picked) return;
    const project = await peekProject(picked);
    if (project) setTemplate(project);
    else toast(t('Aucun projet CStarter ici', 'No CStarter project here'), 'danger', picked);
  };
  const submit = async () => {
    if (!ready) return;
    if (mode === 'starter') await createStarter(location, trimmed, chosen.type, chosen.subsystem);
    else if (template) await createFromTemplate(template.root, location, trimmed);
  };

  return (
    <div className="create">
      <div className="create__page">
        <Button tone="ghost" size="sm" icon={ArrowLeft01Icon} className="create__back" onClick={() => setState({ home: 'start' })}>
          {t('Accueil', 'Home')}
        </Button>
        <PageHeader
          title={t('Nouveau projet', 'New project')}
          actions={
            <Segmented
              value={mode}
              onChange={setMode}
              label={t('Départ', 'Start')}
              items={[
                { value: 'starter', label: t('Neuf', 'New') },
                { value: 'template', label: t('D’un modèle', 'From a template') }
              ]}
            />
          }
        />
        <Section>
          <Reveal when={mode === 'template'}>
            <Row label={t('Modèle', 'Template')}>
              <FolderButton path={template?.root ?? ''} placeholder={t('Choisir un projet', 'Choose a project')} onClick={chooseTemplate} />
            </Row>
          </Reveal>
          <Row label={t('Nom', 'Name')}>
            <Input value={name} onChange={setName} autoFocus onEnter={submit} invalid={Boolean(trimmed) && !valid} />
          </Row>
          <Row label={t('Emplacement', 'Location')}>
            <FolderButton path={folder} placeholder={t('Choisir un dossier', 'Choose a folder')} onClick={chooseLocation} />
          </Row>
          <Reveal when={mode === 'starter'}>
            <Row label="Type" align="start">
              <StartPicker value={start} onChange={setStart} />
            </Row>
          </Reveal>
          <Reveal when={mode === 'starter' && valid}>
            <Row label={t('Fichiers', 'Files')} align="start">
              <ul className="create__files mono">
                {starterFiles(chosen, trimmed).map(path => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
            </Row>
          </Reveal>
          <Reveal when={mode === 'template' && Boolean(template)}>
            <Row label="Targets" align="start">
              <div className="create__targets">
                {(template ? targetOrder(template) : []).map(target => (
                  <Chip key={target.name} icon={typeIcon(target.type)}>
                    {target.name}
                  </Chip>
                ))}
              </div>
            </Row>
          </Reveal>
        </Section>
        <div className="create__actions">
          <Button tone="primary" size="lg" onClick={submit} disabled={!ready}>
            {t('Créer', 'Create')}
          </Button>
        </div>
      </div>
    </div>
  );
}

// Un dossier à choisir : toute la ligne ouvre la boîte de Windows.
function FolderButton({ path, placeholder, onClick }: { path: string; placeholder: string; onClick: () => void }) {
  return (
    <button type="button" className={`flow__pick create__pick${path ? '' : ' flow__pick--empty'}`} onClick={onClick}>
      <Icon icon={Folder01Icon} size={15} className="flow__pick-icon" />
      <span className="mono">
        <bdi>{path || placeholder}</bdi>
      </span>
    </button>
  );
}

// Le premier target : un exécutable console ou fenêtré, une bibliothèque statique ou dynamique.
function StartPicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="starts" role="radiogroup" aria-label="Type">
      {starts().map(start => (
        <button
          key={start.value}
          type="button"
          role="radio"
          aria-checked={start.value === value}
          title={start.title}
          className={`starts__item${start.value === value ? ' starts__item--on' : ''}`}
          onClick={() => onChange(start.value)}
        >
          {start.value === value ? <motion.span layoutId="start-pill" className="starts__pill" transition={{ type: 'spring', bounce: 0, duration: 0.35 }} /> : null}
          <span className="starts__icon">
            <Icon icon={start.icon} size={20} stroke={1.6} />
          </span>
          <span className="starts__label">{start.label}</span>
        </button>
      ))}
    </div>
  );
}
