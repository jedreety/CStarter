// Les bibliothèques, depuis l'accueil : tout le cache,
// %USERPROFILE%\.cstarter\, en paquets. On y installe pour un projet neuf, on y supprime un paquet
// entier ou l'une de ses entrées.

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ArrowDown01Icon, ArrowLeft01Icon, Delete02Icon, PackageIcon, PlusSignIcon } from '@hugeicons/core-free-icons';
import FuseButton from '../reactbits/FuseButton';
import GlideSelect from '../reactbits/GlideSelect';
import { refreshCache, removeEntries } from '../lib/actions';
import { t } from '../lib/i18n';
import { builders, natures } from '../lib/labels';
import { packages, type Package } from '../lib/packages';
import { setState, useStore } from '../lib/store';
import { installFlow } from '../flows/install';
import { Button, Chip, Empty, Icon, PageHeader, Row, Section } from '../components/ui';
import './pages.css';
import './Libraries.css';

export default function Libraries() {
  const cache = useStore(s => s.cache);
  const busy = useStore(s => s.busy);
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  useEffect(() => {
    refreshCache();
  }, []);
  const all = packages(cache ?? []);
  const shown = all.filter(pkg => pkg.key.toLowerCase().includes(filter.trim().toLowerCase()));
  const empty = Boolean(cache) && !all.length;
  return (
    <div className="libraries">
      <div className="libraries__page">
        <Button tone="ghost" size="sm" icon={ArrowLeft01Icon} className="libraries__back" onClick={() => setState({ home: 'start' })}>
          {t('Accueil', 'Home')}
        </Button>
        <PageHeader
          title={t('Bibliothèques', 'Libraries')}
          actions={
            empty ? undefined : (
              <Button tone="primary" icon={PlusSignIcon} onClick={() => installFlow()} disabled={busy}>
                {t('Installer', 'Install')}
              </Button>
            )
          }
        />
        {empty ? (
          <Empty icon={PackageIcon} title={t('Aucune bibliothèque', 'No library')}>
            <Button tone="primary" icon={PlusSignIcon} onClick={() => installFlow()} disabled={busy}>
              {t('Installer', 'Install')}
            </Button>
          </Empty>
        ) : (
          <Section
            action={
              all.length > 8 ? (
                <input className="field field--boxed search" value={filter} placeholder={t('Rechercher', 'Search')} spellCheck={false} onChange={e => setFilter(e.target.value)} />
              ) : undefined
            }
          >
            {shown.map(pkg => (
              <CachedPackage key={pkg.key} pkg={pkg} open={open === pkg.key} onToggle={() => setOpen(open === pkg.key ? null : pkg.key)} />
            ))}
          </Section>
        )}
      </div>
    </div>
  );
}

const ALL = '*';

function CachedPackage({ pkg, open, onToggle }: { pkg: Package; open: boolean; onToggle: () => void }) {
  const [target, setTarget] = useState(ALL);
  const first = pkg.entries[0];
  const source = first.source;
  const origin = source.url || source.original_path || `${source.type}:${source.port || source.ref}`;
  const runtimes = pkg.entries.map(e => e.build.runtime).filter((r): r is string => Boolean(r));
  const platforms = [...new Set(pkg.entries.flatMap(e => e.build.platforms))];
  const removed = target === ALL ? pkg.entries : pkg.entries.filter(entry => entry.name === target);
  return (
    <div className="entry">
      <button className="entry__row" onClick={onToggle} aria-expanded={open}>
        <span className="list-row__icon">
          <Icon icon={PackageIcon} size={15} />
        </span>
        <span className="list-row__title">{pkg.name}</span>
        <span className="list-row__version">{pkg.version}</span>
        <span className="entry__chips">
          <Chip tone="accent">{source.type}</Chip>
          {runtimes.length ? <Chip>{runtimes.join(' · ')}</Chip> : <Chip>{natures()[first.nature]}</Chip>}
          {platforms.length ? <Chip>{platforms.join(' · ')}</Chip> : null}
        </span>
        <Icon icon={ArrowDown01Icon} size={14} className={`entry__chevron${open ? ' entry__chevron--open' : ''}`} />
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            className="entry__details"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: 'spring', bounce: 0, duration: 0.36 }}
          >
            <Row label="Source">
              <span className="mono ellipsis selectable">{origin}</span>
            </Row>
            {source.tag || source.commit ? (
              <Row label={t('Version d’origine', 'Original version')}>
                <span className="mono">{[source.tag, source.commit?.slice(0, 12)].filter(Boolean).join(' · ')}</span>
              </Row>
            ) : null}
            <Row label={t('Construite par', 'Built by')}>
              {builders()[first.build.system] ?? first.build.system}
              {first.build.toolset ? <Chip>{first.build.toolset}</Chip> : null}
            </Row>
            {first.build.flags.length ? (
              <Row label="Options">
                <span className="mono ellipsis selectable">{first.build.flags.join(' ')}</span>
              </Row>
            ) : null}
            <Row label={t('Entrées', 'Entries')}>
              <span className="mono">{pkg.entries.map(e => e.name).join(' · ')}</span>
            </Row>
            {first.libs.length ? (
              <Row label={t('Bibliothèques', 'Libraries')}>
                <span className="mono">{first.libs.join(', ')}</span>
              </Row>
            ) : null}
            {first.requires.length ? (
              <Row label={t('Attend', 'Requires')}>
                <span className="mono">{first.requires.join(', ')}</span>
              </Row>
            ) : null}
            {source.resolvable ? null : <Row label={t('Reconstructible', 'Rebuildable')}>{t('Non, à vendorer', 'No, vendor it')}</Row>}
            <div className="entry__actions">
              {pkg.entries.length > 1 ? (
                <GlideSelect
                  value={target}
                  onChange={setTarget}
                  options={[{ value: ALL, label: t('Tout le paquet', 'The whole package') }, ...pkg.entries.map(entry => ({ value: entry.name, label: entry.name }))]}
                  size="sm"
                  menuWidth={220}
                  surfaceColor="rgba(255,255,255,0.055)"
                  highlightColor="#2a2a31"
                  ariaLabel={t('Ce qui est supprimé', 'What is removed')}
                />
              ) : null}
              <FuseButton
                key={target}
                label={t('Supprimer du cache', 'Remove from the cache')}
                undoLabel={t('Annuler', 'Undo')}
                doneLabel={t('Supprimée', 'Removed')}
                icon={<Icon icon={Delete02Icon} size={14} stroke={1.9} />}
                commitOn="fuseEnd"
                undoWindow={2600}
                size="sm"
                radius={9}
                background="rgba(255,107,107,0.12)"
                color="#ff8f8f"
                fuseColor="#ff6b6b"
                onCommit={() => removeEntries(removed)}
              />
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
