// L'espace de travail d'un projet ouvert : la navigation à gauche, la page au centre, le panneau en bas.
// Une page arrive du côté où elle est dans la navigation : d'en dessous quand on descend, d'au-dessus
// quand on remonte ; la précédente part à l'opposé, plus vite qu'elle n'arrive.

import { useRef, useState } from 'react';
import { AnimatePresence, motion, type Variants } from 'motion/react';
import { FloppyDiskIcon, Undo02Icon } from '@hugeicons/core-free-icons';
import GradualBlur from '../reactbits/GradualBlur';
import SideRays from '../reactbits/SideRays';
import { revert, save } from '../lib/actions';
import { t } from '../lib/i18n';
import { useStore } from '../lib/store';
import Dependencies from '../pages/Dependencies';
import Git from '../pages/Git';
import Overview from '../pages/Overview';
import Settings from '../pages/Settings';
import TargetPage from '../pages/Target';
import BottomPanel from './BottomPanel';
import Sidebar from './Sidebar';
import { Button, Kbd } from './ui';
import './Workspace.css';

function Page({ page }: { page: string }) {
  if (page.startsWith('target:')) return <TargetPage name={page.slice(7)} />;
  switch (page) {
    case 'deps':
      return <Dependencies />;
    case 'git':
      return <Git />;
    case 'settings':
      return <Settings />;
    default:
      return <Overview />;
  }
}

// Le rang d'une page dans la navigation : les quatre destinations, puis les targets dans leur ordre.
const DESTINATIONS = ['overview', 'deps', 'git', 'settings'];
const rank = (page: string, targets: string[]) =>
  page.startsWith('target:') ? DESTINATIONS.length + Math.max(0, targets.indexOf(page.slice(7))) : Math.max(0, DESTINATIONS.indexOf(page));

const PAGE: Variants = {
  enter: (direction: number) => ({ opacity: 0, y: 16 * direction, filter: 'blur(6px)' }),
  shown: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { type: 'spring', bounce: 0, duration: 0.34 } },
  leave: (direction: number) => ({ opacity: 0, y: -10 * direction, filter: 'blur(4px)', transition: { duration: 0.14, ease: [0.4, 0, 1, 1] } })
};

export default function Workspace() {
  const page = useStore(s => s.page);
  const hasModel = useStore(s => Boolean(s.view?.project));
  const targets = useStore(s => s.view?.project?.solution.targets.map(entry => entry.name).join('\n') ?? '');
  const shown = hasModel ? page : 'git';
  const [scrolled, setScrolled] = useState(false);
  // Le sens se fixe au changement de page : un rendu pendant l'animation ne le retourne pas.
  const last = useRef({ page: shown, direction: 1 });
  if (last.current.page !== shown) {
    const names = targets.split('\n');
    last.current = { page: shown, direction: rank(shown, names) >= rank(last.current.page, names) ? 1 : -1 };
  }
  const direction = last.current.direction;
  return (
    <div className="workspace">
      <Sidebar />
      <div className="workspace__main">
        <div className="workspace__rays">
          <SideRays speed={1.4} rayColor1="#8e8cff" rayColor2="#5ec8ff" intensity={1.35} spread={1.8} origin="top-right" saturation={1.15} blend={0.6} falloff={1.9} opacity={0.55} />
        </div>
        <div className="workspace__scroll" onScroll={event => setScrolled(event.currentTarget.scrollTop > 4)}>
          <div className={`workspace__blur workspace__blur--top${scrolled ? ' workspace__blur--on' : ''}`}>
            <GradualBlur position="top" height="3.2rem" strength={1.6} divCount={6} curve="bezier" zIndex={4} />
          </div>
          <AnimatePresence mode="popLayout" initial={false} custom={direction}>
            <motion.div
              key={shown.startsWith('target:') ? `target-${shown}` : shown}
              className="workspace__page"
              data-page={shown}
              custom={direction}
              variants={PAGE}
              initial="enter"
              animate="shown"
              exit="leave"
            >
              <Page page={shown} />
            </motion.div>
          </AnimatePresence>
        </div>
        <UnsavedBar />
        <BottomPanel />
      </div>
    </div>
  );
}

function UnsavedBar() {
  const dirty = useStore(s => Boolean(s.view?.dirty));
  return (
    <AnimatePresence>
      {dirty ? (
        <motion.div
          className="unsaved"
          initial={{ opacity: 0, y: 24, scale: 0.96, filter: 'blur(8px)' }}
          animate={{ opacity: 1, y: 0, scale: 1, filter: 'blur(0px)' }}
          exit={{ opacity: 0, y: 16, scale: 0.97, filter: 'blur(6px)' }}
          transition={{ type: 'spring', bounce: 0.18, duration: 0.45 }}
        >
          <Button tone="ghost" size="sm" icon={Undo02Icon} onClick={revert}>
            {t('Annuler les modifications', 'Discard changes')}
          </Button>
          <Button tone="primary" size="sm" icon={FloppyDiskIcon} onClick={save}>
            {t('Enregistrer', 'Save')}
            <Kbd>Ctrl S</Kbd>
          </Button>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
