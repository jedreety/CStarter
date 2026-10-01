// Les bords de la fenêtre sans cadre : un appui y lance le redimensionnement natif de Windows.

import { call } from '../lib/bridge';
import { useStore } from '../lib/store';

const EDGES = ['top', 'bottom', 'left', 'right', 'topleft', 'topright', 'bottomleft', 'bottomright'];

export default function WindowEdges() {
  const maximized = useStore(s => s.maximized);
  if (maximized) return null;
  return (
    <>
      {EDGES.map(edge => (
        <div
          key={edge}
          className={`edge edge--${edge}`}
          onMouseDown={event => {
            if (event.button === 0) call('window_press', edge);
          }}
        />
      ))}
    </>
  );
}
