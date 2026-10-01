// La navigation du projet : son aperçu, ses dépendances, git et ses
// réglages, puis ses targets. Un fond glisse d'un élément à l'autre.

import { useEffect, useId, useState } from 'react';
import { motion } from 'motion/react';
import type { IconSvgElement } from '@hugeicons/react';
import {
  AppWindowIcon,
  CommandLineIcon,
  DashboardSquare01Icon,
  GitBranchIcon,
  LibraryIcon,
  Logout01Icon,
  PackageIcon,
  PlayIcon,
  PlusSignIcon,
  Plug01Icon,
  Settings02Icon
} from '@hugeicons/core-free-icons';
import { closeProject, navigate, toggleTerminal } from '../lib/actions';
import { t } from '../lib/i18n';
import { targetOrder } from '../lib/model';
import { projectPackages } from '../lib/packages';
import { useStore } from '../lib/store';
import { newTarget } from './NewTarget';
import { Button, Icon, Kbd } from './ui';
import './Sidebar.css';

const TYPE_ICONS: Record<string, IconSvgElement> = { executable: AppWindowIcon, static_lib: LibraryIcon, dynamic_lib: Plug01Icon };

export const typeIcon = (type: string) => TYPE_ICONS[type] ?? LibraryIcon;

// Le terminal s'ouvre par la touche à gauche du 1 (actions.ts) : ` sur un clavier QWERTY, ² sur un
// AZERTY. Le raccourci affiché est celle du clavier de l'utilisateur, que Chromium connaît.
function useBackquote(): string {
  const [key, setKey] = useState('`');
  useEffect(() => {
    const keyboard = (navigator as Navigator & { keyboard?: { getLayoutMap: () => Promise<Map<string, string>> } }).keyboard;
    keyboard
      ?.getLayoutMap()
      .then(map => map.get('Backquote') && setKey(map.get('Backquote')!))
      .catch(() => undefined);
  }, []);
  return key;
}

export default function Sidebar() {
  const project = useStore(s => s.view?.project);
  const page = useStore(s => s.page);
  const changed = useStore(s => s.git?.changes.length ?? 0);
  const missing = useStore(s => {
    const current = s.view?.project;
    if (!current || !s.cache) return 0;
    const known = new Set(s.cache.map(entry => `${entry.name}@${entry.version}`));
    const vendored = new Set(current.vendored.map(ref => `${ref.name}@${ref.version}`));
    return projectPackages(current, s.cache).filter(used => used.refs.some(ref => !known.has(`${ref.name}@${ref.version}`) && !vendored.has(`${ref.name}@${ref.version}`))).length;
  });
  const pill = useId();
  const backquote = useBackquote();
  const shown = project ? page : 'git';

  // Un compteur qui change rebondit : ce qui vient de bouger attire l'œil.
  const item = (value: string, label: string, icon: IconSvgElement, badge?: number, tone?: 'danger', trailing?: IconSvgElement) => (
    <button key={value} type="button" className={`nav__item${shown === value ? ' nav__item--on' : ''}`} aria-current={shown === value ? 'page' : undefined} onClick={() => navigate(value)}>
      {shown === value ? <motion.span layoutId={pill} className="nav__pill" transition={{ type: 'spring', bounce: 0.12, duration: 0.34 }} /> : null}
      <Icon icon={icon} size={16} className="nav__icon" />
      <span className="nav__label">{label}</span>
      {trailing ? <Icon icon={trailing} size={11} stroke={2.4} className="nav__trailing" /> : null}
      {badge ? (
        <motion.span
          key={badge}
          className={`nav__badge${tone ? ` nav__badge--${tone}` : ''}`}
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', bounce: 0.45, duration: 0.4 }}
        >
          {badge}
        </motion.span>
      ) : null}
    </button>
  );

  return (
    <aside className="sidebar">
      <div className="sidebar__scroll">
        <nav className="nav">
          {project ? (
            <>
              {item('overview', t('Aperçu', 'Overview'), DashboardSquare01Icon)}
              {item('deps', t('Dépendances', 'Dependencies'), PackageIcon, missing, 'danger')}
              {item('git', 'Git', GitBranchIcon, changed)}
              {item('settings', t('Réglages', 'Settings'), Settings02Icon)}
            </>
          ) : (
            item('git', 'Git', GitBranchIcon, changed)
          )}
        </nav>
        {project ? (
          <nav className="nav nav--targets">
            <div className="nav__head">
              <span>Targets</span>
              <Button tone="ghost" size="sm" icon={PlusSignIcon} title={t('Nouveau target', 'New target')} onClick={newTarget} />
            </div>
            {targetOrder(project).map(target =>
              item(`target:${target.name}`, target.name, typeIcon(target.type), undefined, undefined, project.solution.startup_target === target.name ? PlayIcon : undefined)
            )}
          </nav>
        ) : null}
      </div>
      <footer className="sidebar__foot">
        <Button tone="ghost" size="sm" icon={CommandLineIcon} onClick={toggleTerminal} className="sidebar__terminal">
          Terminal
          <Kbd>Ctrl {backquote}</Kbd>
        </Button>
        <Button tone="ghost" size="sm" icon={Logout01Icon} onClick={closeProject}>
          {t('Fermer le projet', 'Close the project')}
        </Button>
      </footer>
    </aside>
  );
}
