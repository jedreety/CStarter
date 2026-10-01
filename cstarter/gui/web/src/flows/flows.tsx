// Ouvrir un projet, convertir un projet existant, cloner un dépôt.
// Un dossier converti devient un projet : CStarter montre ce qu'il y trouve, puis le crée de ses
// sources, ou l'importe s'il porte une configuration de build (CMake, Premake, une solution Visual
// Studio), et n'écrit qu'après l'accord de l'utilisateur. Sa lecture paraît dans la barre de titre.

import { useState } from 'react';
import { Delete02Icon, Folder01Icon } from '@hugeicons/core-free-icons';
import FuseButton from '../reactbits/FuseButton';
import { adopt, fail, generate, openProject, operation, pickFolder, toast } from '../lib/actions';
import { ApiError, call } from '../lib/bridge';
import { openSheet, SheetFrame } from '../lib/dialogs';
import { count, t } from '../lib/i18n';
import { importedFrom, targetKinds } from '../lib/labels';
import type { Proposal, RestoreReport, View } from '../lib/model';
import { Button, Chip, Icon, Input, Segmented } from '../components/ui';
import './flows.css';

const baseName = (path: string) => path.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? '';
const kinds = () => Object.entries(targetKinds()).map(([value, label]) => ({ value, label }));

// Ouvrir : le projet du dossier ou d'un dossier au-dessus. Sans projet, la conversion se propose.
export async function openProjectFlow(): Promise<void> {
  const location = await pickFolder();
  if (!location || (await opened(location)) !== false) return;
  if (await openSheet<boolean>(close => <NoProjectSheet location={location} close={close} />, 520)) await scanFolder(location);
}

// Convertir : un dossier qui a déjà son projet s'ouvre, les autres se lisent pour en devenir un.
export async function importFolderFlow(): Promise<void> {
  const location = await pickFolder();
  if (location && (await opened(location)) === false) await scanFolder(location);
}

// Ouvre le projet de location : vrai s'il s'ouvre, faux s'il n'y en a pas, null sur une autre erreur.
async function opened(location: string): Promise<boolean | null> {
  try {
    return await openProject(location, true);
  } catch (error) {
    if (error instanceof ApiError && error.kind === 'ProjectNotFoundError') return false;
    fail(error, t('Ouverture impossible', 'Cannot open'));
    return null;
  }
}

function NoProjectSheet({ location, close }: { location: string; close: (value?: boolean) => void }) {
  return (
    <SheetFrame
      title={t('Aucun projet CStarter ici', 'No CStarter project here')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close(false)}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={() => close(true)}>
            {t('Convertir', 'Convert')}
          </Button>
        </>
      }
    >
      <Folder path={location} />
    </SheetFrame>
  );
}

// Lire un dossier, sans rien y écrire : la pastille de la barre de titre montre que la lecture avance.
function read<T>(location: string, action: () => Promise<T>): Promise<T | undefined> {
  return operation('read', t('Lire', 'Read'), baseName(location), action, false);
}

// Un dossier sans projet : importé s'il porte une configuration de build ou des dépendances, créé de
// ses sources sinon.
async function scanFolder(location: string): Promise<void> {
  const found = await read(location, () => call<{ targets: Proposal[]; notes: string[]; importable: boolean }>('propose', location));
  if (!found) return;
  try {
    if (found.importable) return await importFlow(location);
    if (!found.targets.length) {
      toast(t('Rien à convertir', 'Nothing to convert'), 'danger', t('Aucune source', 'No source'));
      return;
    }
    const choice = await openSheet<{ name: string; types: Record<string, string> }>(close => <CreateSheet location={location} found={found} close={close} />, 620);
    if (!choice) return;
    const view = await call<View>('create', location, choice.name, choice.types);
    adopt(view, 'overview');
    toast(t('Projet créé', 'Project created'), 'success', view.project?.name);
    await generate();
  } catch (error) {
    fail(error, t('Création impossible', 'Cannot create'));
  }
}

function CreateSheet({
  location,
  found,
  close
}: {
  location: string;
  found: { targets: Proposal[]; notes: string[] };
  close: (value?: { name: string; types: Record<string, string> }) => void;
}) {
  const [name, setName] = useState(baseName(location));
  const [types, setTypes] = useState<Record<string, string>>(() => Object.fromEntries(found.targets.map(target => [target.name, target.type])));
  return (
    <SheetFrame
      title={t('Nouveau projet', 'New project')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close()}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={() => close({ name, types })} disabled={!name.trim()}>
            {t('Créer', 'Create')}
          </Button>
        </>
      }
    >
      <div className="sheet__form">
        <div className="sheet__field">
          <label>{t('Nom', 'Name')}</label>
          <Input value={name} onChange={setName} autoFocus />
        </div>
        <Folder path={location} />
        {found.targets.length ? (
          <div className="flow__targets">
            {found.targets.map(target => (
              <ProposalRow key={target.name} proposal={target} type={types[target.name]} onType={type => setTypes({ ...types, [target.name]: type })} />
            ))}
          </div>
        ) : null}
        {found.notes.length ? <Notes title={t('À vérifier', 'To check')} notes={found.notes} /> : null}
      </div>
    </SheetFrame>
  );
}

function Folder({ path }: { path: string }) {
  return (
    <div className="flow__folder mono">
      <Icon icon={Folder01Icon} size={14} className="flow__folder-icon" />
      <span className="flow__folder-path">
        <bdi>{path}</bdi>
      </span>
    </div>
  );
}

function ProposalRow({ proposal, type, onType }: { proposal: Proposal; type?: string; onType?: (type: string) => void }) {
  return (
    <div className="flow__target">
      <div className="flow__target-text">
        <span className="flow__target-name">{proposal.name}</span>
        <span className="flow__target-folder mono">{proposal.folder}</span>
        {proposal.links.length ? <span className="flow__target-links">→ {proposal.links.join(', ')}</span> : null}
      </div>
      {onType && type ? <Segmented size="sm" value={type} onChange={onType} items={kinds()} /> : <Chip>{targetKinds()[proposal.type] ?? proposal.type}</Chip>}
    </div>
  );
}

function Notes({ title, notes, tone = 'warning' }: { title: string; notes: string[]; tone?: 'warning' | 'neutral' }) {
  return (
    <div className={`flow__notes flow__notes--${tone}`}>
      <div className="flow__notes-title">{title}</div>
      <ul>
        {notes.map(note => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  );
}

// Importer

interface Inspection {
  imported_from: string | null;
  name: string | null;
  targets: Proposal[];
  platforms?: string[];
  notes: string[];
  pending: string[];
  info: string[];
  files: string[];
  requirements: { source: { type: string; port: string | null; ref: string | null; tag: string | null }; minimum: string | null }[];
}

async function importFlow(location: string): Promise<void> {
  let execute = false;
  let found = await read(location, () => call<Inspection>('inspect', location, false));
  if (!found) return;
  if (found.pending.length) {
    const pending = found.pending;
    execute = Boolean(
      await openSheet<boolean>(close => (
        <SheetFrame
          title={t('Exécuter le code du projet ?', 'Run the project’s code?')}
          actions={
            <>
              <Button tone="ghost" onClick={() => close(false)}>
                {t('Ne pas exécuter', 'Don’t run')}
              </Button>
              <Button tone="primary" onClick={() => close(true)}>
                {t('Exécuter', 'Run')}
              </Button>
            </>
          }
        >
          <ul className="sheet__paths">
            {pending.map(item => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </SheetFrame>
      ))
    );
    if (execute) found = await read(location, () => call<Inspection>('inspect', location, true));
    if (!found) return;
  }
  if (!found.targets.length) {
    toast(t('Rien à convertir', 'Nothing to convert'), 'danger', t('Aucun target reconnu', 'No target recognized'));
    return;
  }
  const inspected = found;
  const choice = await openSheet<{ name: string; types: Record<string, string> }>(close => <ImportSheet location={location} found={inspected} close={close} />, 660);
  if (!choice) return;
  const result = await operation('import', t('Convertir', 'Convert'), choice.name, () => call<{ view: View; files: string[] }>('import_folder', location, choice.name, execute, choice.types));
  if (!result) return;
  adopt(result.view, 'overview');
  toast(t('Projet converti', 'Project converted'), 'success', result.view.project?.name);
  if (result.files.length) await proposeRemoval(result.files);
}

function ImportSheet({ location, found, close }: { location: string; found: Inspection; close: (value?: { name: string; types: Record<string, string> }) => void }) {
  const [name, setName] = useState(found.name ?? baseName(location));
  const [types, setTypes] = useState<Record<string, string>>(() => Object.fromEntries(found.targets.map(target => [target.name, target.type])));
  const auto = found.imported_from === 'auto';
  return (
    <SheetFrame
      title={t('Convertir en projet CStarter', 'Convert to a CStarter project')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close()}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={() => close({ name, types })} disabled={!name.trim()}>
            {t('Convertir', 'Convert')}
          </Button>
        </>
      }
    >
      <div className="sheet__form">
        <div className="sheet__field">
          <label>{t('Nom', 'Name')}</label>
          <Input value={name} onChange={setName} autoFocus />
        </div>
        <Folder path={location} />
        <div className="flow__chips">
          {found.imported_from ? <Chip tone="accent">{importedFrom()[found.imported_from] ?? found.imported_from}</Chip> : null}
          {(found.platforms ?? []).map(p => (
            <Chip key={p}>{p}</Chip>
          ))}
        </div>
        <div className="flow__targets">
          {found.targets.map(target => (
            <ProposalRow key={target.name} proposal={target} type={types[target.name]} onType={auto ? type => setTypes({ ...types, [target.name]: type }) : undefined} />
          ))}
        </div>
        {found.requirements.length ? (
          <Notes
            title={t('Dépendances à installer', 'Dependencies to install')}
            tone="neutral"
            notes={found.requirements.map(r => `${r.source.type}:${r.source.port ?? r.source.ref}${r.source.tag ? ` ${r.source.tag}` : r.minimum ? ` ≥ ${r.minimum}` : ''}`)}
          />
        ) : null}
        {found.notes.length ? <Notes title={t('Non converti', 'Not converted')} notes={found.notes} /> : null}
        {found.info.length ? <Notes title="git" tone="neutral" notes={found.info} /> : null}
      </div>
    </SheetFrame>
  );
}

async function proposeRemoval(files: string[]): Promise<void> {
  await openSheet<void>(
    close => (
      <SheetFrame
        title={t('Supprimer les anciens fichiers de configuration ?', 'Remove the old configuration files?')}
        actions={
          <>
            <Button tone="ghost" onClick={() => close()}>
              {t('Garder', 'Keep')}
            </Button>
            <FuseButton
              label={t('Supprimer', 'Remove')}
              undoLabel={t('Annuler', 'Undo')}
              doneLabel={t('Supprimés', 'Removed')}
              icon={<Icon icon={Delete02Icon} size={14} stroke={1.9} />}
              commitOn="fuseEnd"
              undoWindow={2600}
              size="sm"
              radius={9}
              background="rgba(255,107,107,0.14)"
              color="#ff8f8f"
              fuseColor="#ff6b6b"
              onCommit={async () => {
                try {
                  const removed = await call<string[]>('remove_old_files', files);
                  toast(count(removed.length, ['fichier supprimé', 'fichiers supprimés'], ['file removed', 'files removed']), 'success');
                } catch (error) {
                  fail(error, t('Suppression impossible', 'Cannot remove'));
                }
                close();
              }}
            />
          </>
        }
      >
        <ul className="sheet__paths mono">
          {files.map(path => (
            <li key={path}>{path}</li>
          ))}
        </ul>
      </SheetFrame>
    ),
    540
  );
  await generate();
}

// Cloner

export async function cloneFlow(): Promise<void> {
  const choice = await openSheet<{ url: string; location: string }>(close => <CloneSheet close={close} />, 560);
  if (!choice) return;
  const result = await operation('clone', t('Cloner', 'Clone'), choice.url, () => call<{ view: View; restore: RestoreReport }>('clone', choice.url, choice.location));
  if (!result) return;
  adopt(result.view, 'overview');
  const missing = [...result.restore.failed, ...result.restore.warnings];
  if (missing.length) {
    toast(t('Restore incomplet', 'Incomplete restore'), 'danger', missing.join('\n'));
    return;
  }
  toast(t('Dépôt cloné', 'Repository cloned'), 'success', result.view.project?.name);
  await generate();
}

function CloneSheet({ close }: { close: (value?: { url: string; location: string }) => void }) {
  const [url, setUrl] = useState('');
  const [parent, setParent] = useState('');
  const name = baseName(url.trim().replace(/\.git$/, '').replace(/:/g, '/'));
  const location = parent && name ? `${parent.replace(/[\\/]+$/, '')}\\${name}` : '';
  const choose = async () => {
    const chosen = await pickFolder();
    if (chosen) setParent(chosen);
  };
  return (
    <SheetFrame
      title={t('Cloner un dépôt', 'Clone a repository')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close()}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={() => close({ url: url.trim(), location })} disabled={!url.trim() || !location}>
            {t('Cloner', 'Clone')}
          </Button>
        </>
      }
    >
      <div className="sheet__form">
        <div className="sheet__field">
          <label>{t('Lien', 'Link')}</label>
          <Input value={url} onChange={setUrl} mono autoFocus placeholder="https://github.com/…" />
        </div>
        <div className="sheet__field">
          <label>{t('Dans', 'Into')}</label>
          <button type="button" className={`flow__pick${parent ? '' : ' flow__pick--empty'}`} onClick={choose}>
            <Icon icon={Folder01Icon} size={15} className="flow__pick-icon" />
            <span className="mono">{location || parent || t('Choisir un dossier', 'Choose a folder')}</span>
          </button>
        </div>
      </div>
    </SheetFrame>
  );
}
