// L'accueil, quand aucun projet n'est ouvert : le dernier projet à reprendre,
// puis créer, ouvrir, convertir un projet existant, cloner, les bibliothèques, et les autres projets
// récents. À droite, le graphe du projet à reprendre, ou du récent sous le pointeur, devant le prisme ;
// sans projet récent, le prisme seul. Le compte GitHub est dans la barre de titre.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowRight01Icon,
  Cancel01Icon,
  FolderAddIcon,
  FolderOpenIcon,
  FolderSyncIcon,
  GitPullRequestIcon,
  PackageIcon,
  PlayIcon,
  Wrench01Icon
} from '@hugeicons/core-free-icons';
import type { IconSvgElement } from '@hugeicons/react';
import LightRays from '../reactbits/LightRays';
import Prism from '../reactbits/Prism';
import ScrollVelocity from '../reactbits/ScrollVelocity';
import { forgetRecent, openProject, peekProject, showPrerequisites } from '../lib/actions';
import { t } from '../lib/i18n';
import type { Project, Recent } from '../lib/model';
import { setState, useStore } from '../lib/store';
import { cloneFlow, importFolderFlow, openProjectFlow } from '../flows/flows';
import { Icon } from '../components/ui';
import { GraphCanvas, layout } from './Overview';
import './Graph.css';
import './Welcome.css';

// Convertir porte seul une ligne d'aide : son nom ne dit pas qu'un projet CMake ou Premake y devient
// un projet CStarter.
const actions = (): { label: string; hint?: string; icon: IconSvgElement; run: () => void }[] => [
  { label: t('Créer un projet', 'Create a project'), icon: FolderAddIcon, run: () => setState({ home: 'create' }) },
  { label: t('Ouvrir un projet', 'Open a project'), icon: FolderOpenIcon, run: () => openProjectFlow() },
  { label: t('Convertir un projet existant', 'Convert an existing project'), hint: 'CMake · Premake · Visual Studio', icon: FolderSyncIcon, run: () => importFolderFlow() },
  { label: t('Cloner un dépôt', 'Clone a repository'), icon: GitPullRequestIcon, run: () => cloneFlow() },
  { label: t('Bibliothèques', 'Libraries'), icon: PackageIcon, run: () => setState({ home: 'libraries' }) }
];

// L'accueil arrive en cascade, en une demi-seconde : chaque élément se clique dès qu'il paraît.
const rise = (delay: number) => ({
  initial: { opacity: 0, y: 12, filter: 'blur(8px)' },
  animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
  transition: { type: 'spring' as const, bounce: 0, duration: 0.5, delay }
});

export default function Welcome() {
  const recent = useStore(s => s.recent);
  const missing = useStore(s => s.prerequisites?.filter(tool => !tool.present).length ?? 0);
  const [hovered, setHovered] = useState<string | null>(null);
  const [last, ...others] = recent;
  const listed = actions();
  return (
    <div className="welcome">
      <div className="welcome__rays">
        <LightRays
          raysOrigin="top-center"
          raysColor="#c9c7ff"
          raysSpeed={0.7}
          lightSpread={0.85}
          rayLength={1.7}
          fadeDistance={1.1}
          saturation={0.9}
          followMouse
          mouseInfluence={0.06}
          noiseAmount={0.04}
          distortion={0.03}
        />
      </div>
      <Stage path={hovered ?? last?.path ?? null} />

      <div className="welcome__content">
        <motion.h1
          className="welcome__title"
          initial={{ opacity: 0, y: 14, filter: 'blur(14px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          transition={{ type: 'spring', bounce: 0, duration: 0.6 }}
        >
          CStarter
        </motion.h1>

        {last ? <Resume entry={last} /> : null}

        <nav className="welcome__actions">
          {listed.map((action, i) => (
            <Action key={action.label} icon={action.icon} label={action.label} hint={action.hint} onClick={action.run} delay={0.1 + i * 0.035} />
          ))}
          {missing ? (
            <Action icon={Wrench01Icon} label={t('Installer les outils', 'Install the tools')} onClick={showPrerequisites} delay={0.1 + listed.length * 0.035} count={missing} />
          ) : null}
        </nav>

        {others.length ? (
          <motion.section className="welcome__recent" {...rise(0.3)}>
            <h2 className="welcome__recent-title">{t('Récents', 'Recent')}</h2>
            <ul onPointerLeave={() => setHovered(null)}>
              {others.map(entry => (
                <li key={entry.path} className="welcome__recent-item" onPointerEnter={() => setHovered(entry.path)}>
                  <button className="welcome__recent-open" onClick={() => openProject(entry.path)}>
                    <span className="welcome__recent-name">{entry.name}</span>
                    <span className="welcome__recent-path">
                      <bdi>{entry.path}</bdi>
                    </span>
                  </button>
                  <button
                    className="welcome__recent-forget"
                    title={t('Retirer des récents', 'Remove from recent')}
                    onClick={() => {
                      setHovered(null);
                      forgetRecent(entry.path);
                    }}
                  >
                    <Icon icon={Cancel01Icon} size={12} stroke={2.2} />
                  </button>
                </li>
              ))}
            </ul>
          </motion.section>
        ) : null}
      </div>

      <div className="welcome__marquee" aria-hidden="true">
        <ScrollVelocity
          texts={['Visual Studio  ·  CMake  ·  Premake  ·  vcpkg  ·  conan  ·  git  ·', 'MSBuild  ·  C++23  ·  x64  ·  ARM64  ·  Debug  ·  Release  ·  Dist  ·']}
          velocity={28}
          numCopies={12}
          className="welcome__marquee-text"
          scrollerClassName="scroller welcome__scroller"
        />
      </div>
    </div>
  );
}

// Une entrée de l'accueil : son icône s'allume au survol, et une flèche dit qu'elle mène ailleurs.
// L'arrivée anime l'enveloppe, l'appui le bouton : l'un ne retarde jamais l'autre.
function Action({ icon, label, hint, count, delay, onClick }: { icon: IconSvgElement; label: string; hint?: string; count?: number; delay: number; onClick: () => void }) {
  return (
    <motion.div {...rise(delay)}>
      <button className="welcome__action" onClick={onClick}>
        <span className="welcome__action-icon">
          <Icon icon={icon} size={18} stroke={1.7} />
        </span>
        <span className="welcome__action-text">
          <span className="welcome__action-label">{label}</span>
          {hint ? <span className="welcome__action-hint">{hint}</span> : null}
        </span>
        {count ? <span className="welcome__action-count">{count}</span> : null}
        <Icon icon={ArrowRight01Icon} size={15} stroke={2} className="welcome__action-go" />
      </button>
    </motion.div>
  );
}

// Le dernier projet ouvert, à part et en premier.
function Resume({ entry }: { entry: Recent }) {
  return (
    <motion.div className="welcome__resume-wrap" {...rise(0.05)}>
      <button className="welcome__resume" onClick={() => openProject(entry.path)}>
        <span className="welcome__resume-icon">
          <Icon icon={PlayIcon} size={18} stroke={1.8} />
        </span>
        <span className="welcome__resume-text">
          <span className="welcome__resume-label">{t('Reprendre', 'Resume')}</span>
          <span className="welcome__resume-name">{entry.name}</span>
          <span className="welcome__resume-path">
            <bdi>{entry.path}</bdi>
          </span>
        </span>
      </button>
    </motion.div>
  );
}

// La scène de droite : le graphe du projet de path, lu sans l'ouvrir, devant le prisme en halo. Un
// graphe qui ne tiendrait qu'en trop petit laisse le prisme seul.
function Stage({ path }: { path: string | null }) {
  const host = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [peeked, setPeeked] = useState<Record<string, Project | null>>({});
  const [shown, setShown] = useState<string | null>(null);
  const cache = useStore(s => s.cache);
  const language = useStore(s => s.language);

  useLayoutEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setSize({ width: element.clientWidth, height: element.clientHeight }));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (path && !(path in peeked)) peekProject(path).then(project => setPeeked(all => ({ ...all, [path]: project })));
  }, [path]);
  // Le graphe affiché ne change qu'une fois le suivant lu : rien ne clignote entre deux.
  useEffect(() => {
    if (!path) setShown(null);
    else if (path in peeked) setShown(path);
  }, [path, peeked]);

  const project = shown ? peeked[shown] : null;
  const graph = useMemo(() => (project ? layout(project, cache) : null), [project, cache, language]);
  const scale = graph ? Math.min(1.6, (size.width - 48) / graph.width, (size.height - 80) / graph.height) : 0;
  const visible = Boolean(project && graph?.nodes.length && scale >= 0.55);

  return (
    <div ref={host} className="welcome__stage">
      <motion.div
        className="welcome__prism"
        initial={{ opacity: 0, scale: 0.92 }}
        animate={visible ? { opacity: 0.45, scale: 1.1, filter: 'blur(16px)' } : { opacity: 1, scale: 1, filter: 'blur(0px)' }}
        transition={{ duration: 0.9, ease: [0.23, 1, 0.32, 1] }}
      >
        <Prism animationType="3drotate" timeScale={0.22} height={3.4} baseWidth={5.4} scale={2.2} glow={1.15} bloom={1} noise={0} hueShift={0.18} colorFrequency={1.05} suspendWhenOffscreen />
      </motion.div>
      <AnimatePresence>
        {visible && project && graph ? (
          <motion.div
            key={shown}
            className="welcome__preview"
            inert
            initial={{ opacity: 0, filter: 'blur(10px)' }}
            animate={{ opacity: 1, filter: 'blur(0px)' }}
            exit={{ opacity: 0, filter: 'blur(10px)' }}
            transition={{ type: 'spring', bounce: 0, duration: 0.5 }}
          >
            <div className="welcome__preview-name">{project.name}</div>
            <div className="welcome__graph" style={{ width: graph.width * scale, height: graph.height * scale }}>
              <div className="welcome__canvas" style={{ width: graph.width, height: graph.height, transform: `scale(${scale})` }}>
                <GraphCanvas graph={graph} startup={project.solution.startup_target} />
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
