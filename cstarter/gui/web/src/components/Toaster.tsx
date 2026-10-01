// Les notifications, en bas à droite : chacune se glisse vers le bas pour disparaître, et sa mèche
// brûle le temps qu'il lui reste, arrêtée tant que le pointeur la survole.

import { AlertCircleIcon, CheckmarkCircle02Icon, InformationCircleIcon } from '@hugeicons/core-free-icons';
import SwipeToast from '../reactbits/SwipeToast';
import { dismissToast } from '../lib/actions';
import { t as translate } from '../lib/i18n';
import { useStore, type Tone } from '../lib/store';
import { Icon } from './ui';
import './Toaster.css';

const LOOK: Record<Tone, { color: string; icon: typeof InformationCircleIcon; duration: number }> = {
  info: { color: '#8e8cff', icon: InformationCircleIcon, duration: 4200 },
  success: { color: '#3ddc97', icon: CheckmarkCircle02Icon, duration: 3600 },
  danger: { color: '#ff6b6b', icon: AlertCircleIcon, duration: 12000 }
};

export default function Toaster() {
  const toasts = useStore(s => s.toasts);
  return (
    <div className="toaster">
      {toasts.map(t => (
        <SwipeToast
          key={t.id}
          inline
          title={t.title}
          description={t.description}
          icon={<Icon icon={LOOK[t.tone].icon} size={18} stroke={1.8} className={`toast-icon toast-icon--${t.tone}`} />}
          fuseColor={LOOK[t.tone].color}
          duration={LOOK[t.tone].duration}
          background="rgba(26, 26, 31, 0.97)"
          color="#f4f4f6"
          width={380}
          radius={14}
          closeButton
          closeLabel={translate('Fermer', 'Close')}
          onClose={() => dismissToast(t.id)}
          className="toast"
        />
      ))}
    </div>
  );
}
