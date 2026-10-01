// La feuille « Nouveau target » : un nom, un type, pour un exécutable son sous-système, et le dossier
// de ses sources, celui de son nom si l'on n'en choisit pas d'autre.

import { useState } from 'react';
import { batch, navigate } from '../lib/actions';
import { openSheet, SheetFrame } from '../lib/dialogs';
import { t } from '../lib/i18n';
import { subsystems, targetKinds } from '../lib/labels';
import type { Call } from '../lib/packages';
import { getState } from '../lib/store';
import { PathField } from './paths';
import { Button, Input, Segmented } from './ui';

export function newTarget(): void {
  openSheet<boolean>(close => <NewTarget close={close} />, 520);
}

function NewTarget({ close }: { close: (value?: boolean) => void }) {
  const hasExecutable = Object.values(getState().view?.project?.targets ?? {}).some(t => t.type === 'executable');
  const [name, setName] = useState('');
  const [type, setType] = useState(hasExecutable ? 'static_lib' : 'executable');
  const [subsystem, setSubsystem] = useState('console');
  const [folder, setFolder] = useState('');
  const trimmed = name.trim();
  const create = async () => {
    if (!trimmed) return;
    const calls: Call[] = [['add_vcxproj', [trimmed, type, subsystem]]];
    if (folder && folder !== trimmed) calls.push(['set_source_dirs', [trimmed, [folder]]]);
    if (await batch(calls)) {
      close(true);
      navigate(`target:${trimmed}`);
    }
  };
  return (
    <SheetFrame
      title={t('Nouveau target', 'New target')}
      actions={
        <>
          <Button tone="ghost" onClick={() => close(false)}>
            {t('Annuler', 'Cancel')}
          </Button>
          <Button tone="primary" onClick={create} disabled={!trimmed}>
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
          <label>Type</label>
          <Segmented value={type} onChange={setType} items={Object.entries(targetKinds()).map(([value, label]) => ({ value, label }))} />
        </div>
        {type === 'executable' ? (
          <div className="sheet__field">
            <label>{t('Sous-système', 'Subsystem')}</label>
            <Segmented value={subsystem} onChange={setSubsystem} items={Object.entries(subsystems()).map(([value, label]) => ({ value, label }))} />
          </div>
        ) : null}
        <div className="sheet__field">
          <label>Sources</label>
          <div className="sheet__boxed">
            <PathField value={folder} placeholder={trimmed || t('Dossier', 'Folder')} onCommit={setFolder} />
          </div>
        </div>
      </div>
    </SheetFrame>
  );
}
