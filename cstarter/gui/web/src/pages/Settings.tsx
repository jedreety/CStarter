// Les réglages : le projet (project.json), la solution (solution.json), le ménage des fichiers
// générés, puis CStarter lui-même : sa langue, sa version, ses
// outils.

import { Delete02Icon, FolderOpenIcon, SystemUpdate01Icon, Wrench01Icon } from '@hugeicons/core-free-icons';
import FuseButton from '../reactbits/FuseButton';
import GlideSelect from '../reactbits/GlideSelect';
import { checkForUpdate, chooseLanguage, clean, edit, reveal, setField, showPrerequisites } from '../lib/actions';
import { t, type Language } from '../lib/i18n';
import { PLATFORMS } from '../lib/labels';
import { targetOrder } from '../lib/model';
import { useProject, useStore } from '../lib/store';
import { DefinesSection } from '../components/editors';
import { PathField } from '../components/paths';
import { Button, Chip, Icon, PageHeader, Row, Section, Segmented, TextField, Toggle } from '../components/ui';
import './pages.css';

export default function Settings() {
  const project = useProject();
  const language = useStore(s => s.language);
  const version = useStore(s => s.version);
  const missing = useStore(s => s.prerequisites?.filter(tool => !tool.present).length ?? 0);
  const solution = project.solution;
  const targets = targetOrder(project);
  const executables = targets.filter(target => target.type === 'executable');
  const startupOptions = (executables.length ? executables : targets).map(target => target.name);

  const togglePlatform = (platform: string, on: boolean) => (on ? edit('add_platform', platform) : edit('remove_platform', platform));
  const makeDefault = (platform: string) => setField(['solution', 'platforms'], [platform, ...solution.platforms.filter(p => p !== platform)]);

  return (
    <>
      <PageHeader title={t('Réglages', 'Settings')} />

      <Section title={t('Projet', 'Project')}>
        <Row label={t('Nom', 'Name')}>
          <TextField value={project.name} onCommit={v => setField(['name'], v)} />
        </Row>
        <Row label="Version">
          <TextField value={project.version} mono width={180} onCommit={v => setField(['version'], v)} />
        </Row>
        <Row label="Visual Studio">
          <Segmented
            size="sm"
            label="Visual Studio"
            value={project.generator}
            onChange={v => setField(['generator'], v)}
            items={[
              { value: 'vs2022', label: '2022' },
              { value: 'vs2026', label: '2026' }
            ]}
          />
        </Row>
        <Row label={t('Dossier', 'Folder')}>
          <span className="mono muted ellipsis selectable">{project.root}</span>
          <Button tone="ghost" size="sm" icon={FolderOpenIcon} onClick={reveal}>
            {t('Afficher', 'Show')}
          </Button>
        </Row>
      </Section>

      <Section title={t('Plateformes', 'Platforms')}>
        {PLATFORMS.map(platform => {
          const on = solution.platforms.includes(platform);
          const first = solution.platforms[0] === platform;
          return (
            <Row key={platform} label={<span className="mono">{platform}</span>}>
              <Toggle on={on} onChange={value => togglePlatform(platform, value)} disabled={on && solution.platforms.length === 1} label={platform} />
              {first ? <Chip tone="accent">{t('Par défaut', 'Default')}</Chip> : null}
              {on && !first ? (
                <Button tone="ghost" size="sm" onClick={() => makeDefault(platform)}>
                  {t('Définir par défaut', 'Make default')}
                </Button>
              ) : null}
            </Row>
          );
        })}
      </Section>

      <Section title="Solution">
        <Row label={t('Target de démarrage', 'Startup target')}>
          {startupOptions.length ? (
            <GlideSelect
              value={solution.startup_target ?? ''}
              placeholder={t('Aucun', 'None')}
              onChange={v => edit('set_startup_target', v)}
              options={startupOptions}
              menuWidth={220}
              surfaceColor="rgba(255,255,255,0.055)"
              highlightColor="#2a2a31"
              ariaLabel={t('Target de démarrage', 'Startup target')}
            />
          ) : (
            <span className="faint">{t('Aucun target', 'No target')}</span>
          )}
        </Row>
        <Row label={t('Dossier du .sln', '.sln folder')}>
          <PathField value={solution.sln_output} onCommit={v => edit('set_sln_output', v || '.')} />
        </Row>
      </Section>

      <DefinesSection
        title={t('Defines globaux', 'Global defines')}
        defines={solution.global_defines}
        onSet={(name, value) => edit('add_global_define', name, value)}
        onRemove={name => edit('remove_global_define', name)}
      />

      <Section title="Maintenance">
        <Row label={t('Fichiers générés et sorties', 'Generated files and outputs')}>
          <FuseButton
            label={t('Nettoyer', 'Clean')}
            undoLabel={t('Annuler', 'Undo')}
            doneLabel={t('Nettoyé', 'Cleaned')}
            icon={<Icon icon={Delete02Icon} size={14} stroke={1.9} />}
            commitOn="fuseEnd"
            undoWindow={2400}
            size="sm"
            radius={9}
            background="rgba(255,255,255,0.055)"
            color="#f4f4f6"
            fuseColor="#ff6b6b"
            onCommit={clean}
          />
        </Row>
      </Section>

      <Section title="CStarter">
        <Row label={t('Langue', 'Language')}>
          <Segmented<Language>
            size="sm"
            label={t('Langue', 'Language')}
            value={language}
            onChange={chooseLanguage}
            items={[
              { value: 'fr', label: 'Français' },
              { value: 'en', label: 'English' }
            ]}
          />
        </Row>
        <Row label="Version">
          <span className="mono">{version}</span>
          <Button tone="ghost" size="sm" icon={SystemUpdate01Icon} onClick={checkForUpdate}>
            {t('Rechercher une mise à jour', 'Check for updates')}
          </Button>
        </Row>
        <Row label={t('Outils', 'Tools')}>
          {missing ? <Chip tone="warning">{t(`${missing} à installer`, `${missing} to install`)}</Chip> : <Chip tone="success">{t('Tous présents', 'All present')}</Chip>}
          <Button tone="ghost" size="sm" icon={Wrench01Icon} onClick={showPrerequisites}>
            {t('Afficher', 'Show')}
          </Button>
        </Row>
      </Section>
    </>
  );
}
