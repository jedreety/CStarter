// La marque de CStarter : le C du langage, et dans son ouverture le triangle qui lance, sur une tuile
// violette unie. Le même dessin fait l'icône de l'exécutable (scripts/distribution/cstarter.ico).

import { useId } from 'react';

export default function Logo({ size = 20 }: { size?: number }) {
  const id = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" style={{ flex: 'none' }}>
      <defs>
        <filter id={`${id}-lift`} x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="1.4" stdDeviation="1.4" floodColor="#15116b" floodOpacity="0.35" />
        </filter>
      </defs>
      <rect x="2" y="2" width="60" height="60" rx="15" fill="#6c68f2" />
      <rect x="2.5" y="2.5" width="59" height="59" rx="14.5" fill="none" stroke="#fff" strokeOpacity="0.22" />
      <g filter={`url(#${id}-lift)`} fill="#fff" stroke="#fff">
        <path d="M 41.8 21.2 A 15.5 15.5 0 1 0 41.8 42.8" fill="none" strokeWidth="7" strokeLinecap="round" />
        <path d="M 37 27 L 49 32 L 37 37 Z" strokeWidth="3.2" strokeLinejoin="round" />
      </g>
    </svg>
  );
}
