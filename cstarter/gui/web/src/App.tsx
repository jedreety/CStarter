// La fenêtre : barre de titre, puis l'accueil, les bibliothèques du cache, la création d'un projet, ou
// l'espace de travail du projet ouvert. Elle se redessine entière quand la langue change.
// Un écran entre pendant que le précédent s'efface : rien n'attend la fin d'une animation. Avec la
// réduction des animations de Windows, les déplacements cèdent la place à des fondus.

import { AnimatePresence, MotionConfig, motion } from 'motion/react';
import { panelHeight, useStore, useWindowHeight } from './lib/store';
import Sheets from './components/Sheets';
import TitleBar from './components/TitleBar';
import Toaster from './components/Toaster';
import WindowEdges from './components/WindowEdges';
import Workspace from './components/Workspace';
import Create from './pages/Create';
import Libraries from './pages/Libraries';
import Welcome from './pages/Welcome';
import './App.css';

export default function App() {
  const booted = useStore(s => s.booted);
  const open = useStore(s => Boolean(s.view?.root));
  const home = useStore(s => s.home);
  const panel = useStore(s => s.panel);
  const windowHeight = useWindowHeight();
  const dirty = useStore(s => Boolean(s.view?.dirty));
  useStore(s => s.language); // chaque texte se relit dans la nouvelle langue
  const bottom = panel.open ? panelHeight(panel.height, windowHeight) : 38;
  // Les notifications montent au-dessus du panneau du bas et de la barre des modifications.
  return (
    <MotionConfig reducedMotion="user">
      <div className="app" style={{ ['--panel-height' as string]: `${open ? bottom : 0}px`, ['--unsaved' as string]: dirty ? '62px' : '0px' }}>
        <TitleBar />
        <main className="app__main">
          <AnimatePresence initial={false}>
            {booted ? (
              <motion.div
                key={open ? 'workspace' : home}
                className="app__screen"
                initial={{ opacity: 0, scale: 0.985, filter: 'blur(8px)' }}
                animate={{ opacity: 1, scale: 1, filter: 'blur(0px)', transition: { type: 'spring', bounce: 0, duration: 0.42 } }}
                exit={{ opacity: 0, scale: 1.01, filter: 'blur(6px)', transition: { duration: 0.16, ease: [0.4, 0, 1, 1] } }}
              >
                {open ? <Workspace /> : home === 'libraries' ? <Libraries /> : home === 'create' ? <Create /> : <Welcome />}
              </motion.div>
            ) : null}
          </AnimatePresence>
        </main>
        <Toaster />
        <Sheets />
        <WindowEdges />
      </div>
    </MotionConfig>
  );
}
