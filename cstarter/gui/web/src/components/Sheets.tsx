// Les feuilles ouvertes, la dernière au-dessus : un voile qui assombrit la fenêtre, et une surface
// qui se matérialise, le flou et l'échelle ensemble.

import { useEffect } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useStore } from '../lib/store';
import './Sheets.css';

export default function Sheets() {
  const sheets = useStore(s => s.sheets);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && sheets.length) {
        event.preventDefault();
        sheets[sheets.length - 1].resolve(undefined);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [sheets]);
  return (
    <AnimatePresence>
      {sheets.map((sheet, index) => (
        <motion.div
          key={sheet.id}
          className="sheet-layer"
          style={{ zIndex: 200 + index }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.16 } }}
          transition={{ duration: 0.18 }}
          onPointerDown={event => {
            if (event.target === event.currentTarget) sheet.resolve(undefined);
          }}
        >
          <motion.div
            className="sheet"
            role="dialog"
            aria-modal="true"
            style={{ width: sheet.width ?? 480 }}
            initial={{ opacity: 0, scale: 0.94, y: 12, filter: 'blur(10px)' }}
            animate={{ opacity: 1, scale: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, scale: 0.97, y: 6, filter: 'blur(6px)', transition: { duration: 0.14 } }}
            transition={{ type: 'spring', bounce: 0, duration: 0.32 }}
          >
            {sheet.render(sheet.resolve)}
          </motion.div>
        </motion.div>
      ))}
    </AnimatePresence>
  );
}
