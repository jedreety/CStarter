// Ce que chaque target du projet lie : des bibliothèques du cache,
// en paquets liés d'un coup à toutes ses configurations, et d'autres targets. Le + d'un target, ou
// Ajouter au bas de sa liste, ouvre ce qu'il peut lier ; la croix retire. Installer, en haut à
// droite, ajoute une bibliothèque au cache.

import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Archive02Icon, Cancel01Icon, CloudDownloadIcon, Download04Icon, HierarchySquare01Icon, PackageIcon, PlusSignIcon } from '@hugeicons/core-free-icons';
import GlideSelect from '../reactbits/GlideSelect';
import { addPlatforms, edit, linkPackage, navigate, refreshCache, restore, unlinkPackage, unvendorPackage, vendorPackage } from '../lib/actions';
import { t } from '../lib/i18n';
import { targetKinds } from '../lib/labels';
import type { Dependency, Link, Project, Target } from '../lib/model';
import { targetOrder } from '../lib/model';
import { linkedPackages, packages, type Linked, type Package } from '../lib/packages';
import { useProject, useStore } from '../lib/store';
import { installFlow } from '../flows/install';
import { newTarget } from '../components/NewTarget';
import { MenuButton, type MenuItem } from '../components/Popover';
import { typeIcon } from '../components/Sidebar';
import { Button, Chip, Empty, Icon, PageHeader, Section } from '../components/ui';
import './pages.css';

const ROW = {
  initial: { opacity: 0, height: 0 },
  animate: { opacity: 1, height: 'auto' },
  exit: { opacity: 0, height: 0 },
  transition: { type: 'spring' as const, bounce: 0, duration: 0.32 }
};

const known = (cache: Dependency[] | null, name: string, version: string) => Boolean(cache?.some(e => e.name === name && e.version === version));

export default function Dependencies() {
  const project = useProject();
  const cache = useStore(s => s.cache);
  const busy = useStore(s => s.busy);
  useEffect(() => {
    refreshCache();
  }, []);
  const all = useMemo(() => packages(cache ?? []), [cache]);
  const targets = targetOrder(project);
  // Restaurer ne paraît que lorsqu'une entrée liée manque au cache, sans être vendorée.
  const absent = targets.some(target =>
    Object.values(target.dependencies).some(refs => refs.some(ref => !known(cache, ref.name, ref.version) && !project.vendored.some(v => v.name === ref.name && v.version === ref.version)))
  );
  return (
    <>
      <PageHeader
        title={t('Dépendances', 'Dependencies')}
        actions={
          <>
            {absent && cache ? (
              <Button icon={CloudDownloadIcon} onClick={restore} disabled={busy}>
                {t('Restaurer', 'Restore')}
              </Button>
            ) : null}
            <Button tone="primary" icon={PlusSignIcon} onClick={() => installFlow()} disabled={busy}>
              {t('Installer', 'Install')}
            </Button>
          </>
        }
      />
      {targets.length ? (
        targets.map(target => <TargetDependencies key={target.name} project={project} target={target} all={all} cache={cache} />)
      ) : (
        <Empty icon={HierarchySquare01Icon} title={t('Aucun target', 'No target')}>
          <Button tone="primary" icon={PlusSignIcon} onClick={newTarget}>
            {t('Nouveau target', 'New target')}
          </Button>
        </Empty>
      )}
    </>
  );
}

// Si from lie to, directement ou par d'autres targets : lier to à from ferait un cycle.
function reaches(project: Project, from: string, to: string): boolean {
  const seen = new Set<string>();
  const waiting = [from];
  while (waiting.length) {
    const name = waiting.pop()!;
    if (name === to) return true;
    if (seen.has(name)) continue;
    seen.add(name);
    waiting.push(...(project.solution.targets.find(entry => entry.name === name)?.depends_on ?? []).map(link => link.target));
  }
  return false;
}

function TargetDependencies({ project, target, all, cache }: { project: Project; target: Target; all: Package[]; cache: Dependency[] | null }) {
  const linked = linkedPackages(target, cache);
  const links = project.solution.targets.find(entry => entry.name === target.name)?.depends_on ?? [];
  const available = all.filter(pkg => !linked.some(l => l.key === pkg.key));
  const candidates = targetOrder(project).filter(
    other => other.name !== target.name && other.type !== 'executable' && !links.some(link => link.target === other.name) && !reaches(project, other.name, target.name)
  );
  const kinds = targetKinds();
  const libraries = t('Bibliothèques', 'Libraries');
  const items: MenuItem[] = [
    ...available.map(pkg => ({ value: `pkg:${pkg.key}`, label: pkg.name, text: pkg.key, tag: pkg.version, icon: PackageIcon, group: libraries })),
    ...candidates.map(other => ({ value: `target:${other.name}`, label: other.name, icon: typeIcon(other.type), tag: kinds[other.type], group: 'Targets' })),
    { value: 'install', label: t('Installer une bibliothèque', 'Install a library'), icon: Download04Icon, sticky: true, separated: available.length + candidates.length > 0 }
  ];
  const select = (value: string) => {
    if (value.startsWith('pkg:')) {
      const pkg = all.find(p => p.key === value.slice(4));
      if (pkg) linkPackage(target.name, pkg);
    } else if (value.startsWith('target:')) edit('add_project_reference', target.name, value.slice(7));
    else installFlow(target.name);
  };
  const menu = { items, onSelect: select, filter: items.length > 8 };
  return (
    <Section
      title={
        <button type="button" className="dep-target" onClick={() => navigate(`target:${target.name}`)}>
          <Icon icon={typeIcon(target.type)} size={16} className="dep-target__icon" />
          {target.name}
        </button>
      }
      action={<MenuButton {...menu} icon={PlusSignIcon} title={t(`Ajouter à ${target.name}`, `Add to ${target.name}`)} />}
    >
      <AnimatePresence initial={false}>
        {linked.map(pkg => (
          <LinkedPackage key={pkg.key} project={project} target={target} linked={pkg} all={all} cache={cache} />
        ))}
        {links.map(link => (
          <LinkedTarget key={link.target} target={target} dependency={project.targets[link.target]} link={link} />
        ))}
      </AnimatePresence>
      <MenuButton {...menu} icon={PlusSignIcon} label={t('Ajouter', 'Add')} align="start" className="add-row" />
    </Section>
  );
}

// Un paquet lié : ses configurations s'allument quand elles le lient, un clic en lie ou en délie une.
// L'archive le vendore dans .cstarter/vendor/, ou, allumée, le rend au cache.
function LinkedPackage({ project, target, linked, all, cache }: { project: Project; target: Target; linked: Linked; all: Package[]; cache: Dependency[] | null }) {
  const busy = useStore(s => s.busy);
  const pkg = all.find(p => p.key === linked.key);
  const refs = Object.values(linked.refs);
  const vendored = refs.every(ref => project.vendored.some(v => v.name === ref.name && v.version === ref.version));
  const absent = !vendored && refs.some(ref => !known(cache, ref.name, ref.version));
  const platforms = project.solution.platforms;
  const lacking = pkg ? [...new Set(pkg.entries.filter(e => e.nature !== 'header_only').flatMap(e => platforms.filter(p => !e.build.platforms.includes(p))))] : [];
  return (
    <motion.div className="list-row dep-row" {...ROW}>
      <span className="list-row__icon">
        <Icon icon={PackageIcon} size={15} />
      </span>
      <span className="list-row__title">{linked.name}</span>
      <span className="list-row__version">{linked.version}</span>
      {absent ? <Chip tone="danger">{t('Absente du cache', 'Missing from the cache')}</Chip> : vendored ? <Chip tone="accent">{t('Vendorée', 'Vendored')}</Chip> : null}
      {lacking.length && pkg ? (
        <Button tone="secondary" size="sm" icon={PlusSignIcon} disabled={busy} onClick={() => addPlatforms(pkg.entries, platforms)}>
          {lacking.join(' · ')}
        </Button>
      ) : null}
      <span className="list-row__end">
        <span className="config-pills">
          {target.configurations.map(c => {
            const on = Boolean(linked.refs[c.name]);
            return (
              <button
                key={c.name}
                type="button"
                className={`config-pill${on ? ' config-pill--on' : ''}`}
                aria-pressed={on}
                title={on ? t(`Lié en ${c.name} · délier`, `Linked in ${c.name} · unlink`) : t(`Lier en ${c.name}`, `Link in ${c.name}`)}
                disabled={!on && !pkg}
                onClick={() => (on ? unlinkPackage(target.name, linked, c.name) : pkg && linkPackage(target.name, pkg, c.name))}
              >
                {c.name}
              </button>
            );
          })}
        </span>
        {vendored ? (
          <Button tone="ghost" size="sm" icon={Archive02Icon} title={t('Rendre au cache', 'Give back to the cache')} className="dep-row__vendored" onClick={() => unvendorPackage(refs)} />
        ) : absent ? null : (
          <Button tone="ghost" size="sm" icon={Archive02Icon} title={t('Vendorer dans le projet', 'Vendor into the project')} onClick={() => vendorPackage(refs)} />
        )}
        <Button tone="ghost" size="sm" icon={Cancel01Icon} title={t('Retirer', 'Remove')} onClick={() => unlinkPackage(target.name, linked)} />
      </span>
    </motion.div>
  );
}

// Un target lié, et la configuration qu'il construit pour chacune de celles du target. Une
// configuration sans homonyme chez lui en attend une ; les autres construisent la même, sauf si le
// + leur en fait choisir une autre.
function LinkedTarget({ target, dependency, link }: { target: Target; dependency?: Target; link: Link }) {
  const theirs = dependency?.configurations.map(c => c.name) ?? [];
  const [added, setAdded] = useState<string[]>([]);
  const mapped = target.configurations.filter(c => link.config_mapping[c.name] !== undefined || !theirs.includes(c.name) || added.includes(c.name));
  const others = target.configurations.filter(c => !mapped.includes(c));
  const change = (mine: string, value: string) => {
    const next = { ...link.config_mapping };
    if (value === mine) delete next[mine];
    else next[mine] = value;
    edit('set_project_reference', target.name, link.target, next);
  };
  return (
    <motion.div className="list-row list-row--stack" {...ROW}>
      <div className="list-row__line">
        <span className="list-row__icon">
          <Icon icon={typeIcon(dependency?.type ?? '')} size={15} />
        </span>
        <button className="list-row__link" onClick={() => navigate(`target:${link.target}`)}>
          {link.target}
        </button>
        <span className="list-row__version">{dependency ? targetKinds()[dependency.type] : ''}</span>
        <span className="list-row__end">
          {others.length ? (
            <MenuButton
              icon={PlusSignIcon}
              title={t('Choisir la configuration construite', 'Choose the built configuration')}
              width={220}
              items={others.map(c => ({ value: c.name, label: c.name, tag: `→ ${c.name}` }))}
              onSelect={name => setAdded([...added, name])}
            />
          ) : null}
          <Button tone="ghost" size="sm" icon={Cancel01Icon} title={t('Retirer', 'Remove')} onClick={() => edit('remove_project_reference', target.name, link.target)} />
        </span>
      </div>
      {mapped.length ? (
        <div className="mapping">
          {mapped.map(c => (
            <div key={c.name} className="mapping__row">
              <span className="mapping__mine">{c.name}</span>
              <span className="mapping__arrow">→</span>
              <GlideSelect
                value={link.config_mapping[c.name] ?? (theirs.includes(c.name) ? c.name : '')}
                placeholder={t('À choisir', 'To choose')}
                onChange={v => change(c.name, v)}
                options={theirs}
                menuWidth={170}
                size="sm"
                surfaceColor="rgba(255,255,255,0.055)"
                highlightColor="#2a2a31"
                ariaLabel={t(`Configuration de ${link.target} pour ${c.name}`, `${link.target} configuration for ${c.name}`)}
              />
            </div>
          ))}
        </div>
      ) : null}
    </motion.div>
  );
}
