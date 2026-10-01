// L'aperçu du projet : son graphe. Les targets en couches, chaque
// consommateur au-dessus de ce qu'il lie, et en bas les paquets du cache que les targets lient. Un
// clic sur un target l'ouvre. Le graphe s'ajuste à la place qu'il a, se déplace en restant appuyé,
// garde son élan au lâcher, revient s'il s'éloigne trop, se zoome à la molette autour du pointeur ou
// par ses boutons, et un double clic le remet à sa place.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { animate, motion, useDragControls, useMotionValue, useTransform } from 'motion/react';
import { CenterFocusIcon, HierarchySquare01Icon, MinusSignIcon, PackageIcon, PlusSignIcon } from '@hugeicons/core-free-icons';
import { navigate } from '../lib/actions';
import { t } from '../lib/i18n';
import { GENERATORS, targetTypes } from '../lib/labels';
import type { Dependency, Project } from '../lib/model';
import { targetOrder } from '../lib/model';
import { linkedPackages } from '../lib/packages';
import { useProject, useStore } from '../lib/store';
import { newTarget } from '../components/NewTarget';
import { typeIcon } from '../components/Sidebar';
import { Button, Chip, Empty, Icon, PageHeader } from '../components/ui';
import './Graph.css';

const W = 188;
const H = 60;
const STEP_X = 232;
const STEP_Y = 140;
const PAD = 40;
const ENTRY_W = 150;
const ENTRY_H = 38;
// L'ajustement : assez grand pour se lire, jamais démesuré sur un grand écran.
const FIT_MIN = 0.7;
const FIT_MAX = 1.6;
// Le zoom de l'utilisateur, autour de l'ajustement.
const ZOOM_MIN = 0.35;
const ZOOM_MAX = 2.5;

interface Node {
  id: string;
  kind: 'target' | 'entry';
  label: string;
  detail: string;
  type?: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Edge {
  from: string;
  to: string;
  kind: 'link' | 'entry';
  label?: string;
}

export interface Layout {
  nodes: Node[];
  edges: Edge[];
  width: number;
  height: number;
}

// Le graphe d'un projet, aussi celui que l'accueil montre du projet à reprendre.
export function layout(project: Project, cache: Dependency[] | null): Layout {
  const targets = targetOrder(project);
  const types = targetTypes();
  const links = new Map(project.solution.targets.map(entry => [entry.name, entry.depends_on]));
  const consumers = new Map<string, string[]>(targets.map(target => [target.name, []]));
  links.forEach((deps, name) => deps.forEach(link => consumers.get(link.target)?.push(name)));

  // Les consommateurs d'abord : la profondeur d'un target est celle de son consommateur le plus bas, plus un.
  const depth = new Map<string, number>();
  const waiting = new Map(targets.map(target => [target.name, consumers.get(target.name)!.length]));
  const ready = targets.filter(target => waiting.get(target.name) === 0).map(target => target.name);
  while (ready.length) {
    const name = ready.shift()!;
    const mine = Math.max(0, ...consumers.get(name)!.map(c => (depth.get(c) ?? 0) + 1));
    depth.set(name, mine);
    for (const link of links.get(name) ?? []) {
      waiting.set(link.target, waiting.get(link.target)! - 1);
      if (waiting.get(link.target) === 0) ready.push(link.target);
    }
  }
  targets.forEach(target => depth.has(target.name) || depth.set(target.name, 0));

  const layers: string[][] = [];
  const startup = project.solution.startup_target;
  [...targets]
    .sort((a, b) => Number(b.name === startup) - Number(a.name === startup) || a.name.localeCompare(b.name))
    .forEach(target => (layers[depth.get(target.name)!] ??= []).push(target.name));

  const packages = new Map<string, { name: string; version: string; users: Set<string> }>();
  targets.forEach(target =>
    linkedPackages(target, cache).forEach(linked => {
      if (!packages.has(linked.key)) packages.set(linked.key, { name: linked.name, version: linked.version, users: new Set() });
      packages.get(linked.key)!.users.add(target.name);
    })
  );

  const widest = Math.max(1, ...layers.map(l => l.length), Math.ceil(packages.size * ((ENTRY_W + 24) / STEP_X)));
  const width = PAD * 2 + (widest - 1) * STEP_X + W;
  const nodes: Node[] = [];
  layers.forEach((layer, row) =>
    layer.forEach((name, i) => {
      const target = project.targets[name];
      const x = width / 2 + (i - (layer.length - 1) / 2) * STEP_X - W / 2;
      nodes.push({ id: name, kind: 'target', label: name, detail: types[target.type], type: target.type, x, y: PAD + row * STEP_Y, w: W, h: H });
    })
  );
  const entryRow = PAD + layers.length * STEP_Y - 10;
  [...packages.keys()].sort().forEach((key, i, all) => {
    const step = ENTRY_W + 24;
    const x = width / 2 + (i - (all.length - 1) / 2) * step - ENTRY_W / 2;
    const pkg = packages.get(key)!;
    nodes.push({ id: key, kind: 'entry', label: pkg.name, detail: pkg.version, x, y: entryRow, w: ENTRY_W, h: ENTRY_H });
  });

  const edges: Edge[] = [];
  links.forEach((deps, name) =>
    deps.forEach(link => {
      const mapping = Object.entries(link.config_mapping)
        .map(([a, b]) => `${a}→${b}`)
        .join('  ');
      edges.push({ from: name, to: link.target, kind: 'link', label: mapping || undefined });
    })
  );
  packages.forEach((pkg, key) => pkg.users.forEach(user => edges.push({ from: user, to: key, kind: 'entry' })));
  const height = (packages.size ? entryRow + ENTRY_H : PAD + (layers.length - 1) * STEP_Y + H) + PAD;
  return { nodes, edges, width, height };
}

export default function Overview() {
  const project = useProject();
  const cache = useStore(s => s.cache);
  const language = useStore(s => s.language);
  const graph = useMemo(() => layout(project, cache), [project, cache, language]);
  const [hovered, setHovered] = useState<string | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ width: 0, height: 0 });
  const [zoom, setZoom] = useState(1);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const grid = useTransform(() => `${x.get()}px ${y.get()}px`);
  const dragged = useRef(false);
  // Le déplacement part de n'importe où sur la toile, pas seulement du graphe.
  const controls = useDragControls();
  const fit = view.width ? Math.min(FIT_MAX, Math.max(FIT_MIN, Math.min(view.width / graph.width, view.height / graph.height))) : 1;
  const scale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, fit * zoom));
  const width = graph.width * scale;
  const height = graph.height * scale;
  const center = { x: (view.width - width) / 2, y: height > view.height ? 0 : (view.height - height) / 2 };
  // Une bande du graphe reste toujours visible ; au-delà, il revient comme tiré par un élastique.
  const keep = 96;
  const bounds = {
    left: Math.min(center.x, keep - width),
    right: Math.max(center.x, view.width - keep),
    top: Math.min(center.y, keep - height),
    bottom: Math.max(center.y, view.height - keep)
  };

  useLayoutEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setView({ width: element.clientWidth, height: element.clientHeight }));
    observer.observe(element);
    return () => observer.disconnect();
  }, [graph.nodes.length > 0]);
  // Une autre fenêtre ou un autre graphe : l'ajustement repart, au centre.
  useEffect(() => {
    setZoom(1);
    x.set((view.width - graph.width * fit) / 2);
    y.set(graph.height * fit > view.height ? 0 : (view.height - graph.height * fit) / 2);
  }, [view.width, view.height, graph.width, graph.height]);

  // Zoomer autour d'un point de la toile : ce qui est sous lui y reste.
  const zoomAt = (factor: number, px = view.width / 2, py = view.height / 2) => {
    const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, scale * factor));
    const ratio = next / scale;
    x.set(px - (px - x.get()) * ratio);
    y.set(py - (py - y.get()) * ratio);
    setZoom(next / fit);
  };
  const zoomer = useRef(zoomAt);
  zoomer.current = zoomAt;
  // La molette zoome au lieu de faire défiler la page : un écouteur non passif, qui peut l'empêcher.
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const box = element.getBoundingClientRect();
      zoomer.current(Math.exp(-event.deltaY * 0.0015), event.clientX - box.left, event.clientY - box.top);
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, [graph.nodes.length > 0]);

  const recenter = () => {
    setZoom(1);
    const w = graph.width * fit;
    const h = graph.height * fit;
    animate(x, (view.width - w) / 2, { type: 'spring', bounce: 0, duration: 0.5 });
    animate(y, h > view.height ? 0 : (view.height - h) / 2, { type: 'spring', bounce: 0, duration: 0.5 });
  };

  return (
    <>
      <PageHeader
        title={project.name}
        meta={
          <>
            <Chip tone="accent">{GENERATORS[project.generator] ?? project.generator}</Chip>
            <Chip>{project.solution.platforms.join(' · ')}</Chip>
          </>
        }
      />
      {graph.nodes.length ? (
        <div className="graph-frame">
          <motion.div
            ref={host}
            className="graph"
            style={{ backgroundPosition: grid }}
            onPointerDown={event => controls.start(event)}
            onDoubleClick={event => !(event.target as HTMLElement).closest('.graph__node') && recenter()}
          >
            <motion.div
              className="graph__canvas"
              drag
              dragControls={controls}
              dragListener={false}
              dragConstraints={bounds}
              dragElastic={0.14}
              dragTransition={{ power: 0.18, timeConstant: 220, bounceStiffness: 280, bounceDamping: 30 }}
              onDragStart={() => (dragged.current = true)}
              onDragEnd={() => requestAnimationFrame(() => (dragged.current = false))}
              style={{ x, y, scale, originX: 0, originY: 0, width: graph.width, height: graph.height }}
            >
              <GraphCanvas
                graph={graph}
                startup={project.solution.startup_target}
                hovered={hovered}
                onHover={setHovered}
                onOpen={node => !dragged.current && navigate(node.kind === 'target' ? `target:${node.id}` : 'deps')}
              />
            </motion.div>
          </motion.div>
          <div className="graph__zoom">
            <Button tone="ghost" size="sm" icon={MinusSignIcon} title={t('Zoom arrière', 'Zoom out')} onClick={() => zoomAt(1 / 1.25)} />
            <Button tone="ghost" size="sm" icon={CenterFocusIcon} title={t('Ajuster', 'Fit')} onClick={recenter} />
            <Button tone="ghost" size="sm" icon={PlusSignIcon} title={t('Zoom avant', 'Zoom in')} onClick={() => zoomAt(1.25)} />
          </div>
        </div>
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

// Le graphe dessiné : ses liens, puis ses nœuds. L'aperçu le déplace et le zoome ; l'accueil le
// montre sans qu'on y touche.
export function GraphCanvas({
  graph,
  startup,
  hovered = null,
  onHover,
  onOpen
}: {
  graph: Layout;
  startup: string | null;
  hovered?: string | null;
  onHover?: (id: string | null) => void;
  onOpen?: (node: Node) => void;
}) {
  const byId = new Map(graph.nodes.map(n => [n.id, n]));
  const connected = (id: string) => !hovered || id === hovered || graph.edges.some(e => (e.from === hovered && e.to === id) || (e.to === hovered && e.from === id));
  return (
    <>
      <svg className="graph__edges" width={graph.width} height={graph.height}>
        <defs>
          <marker id="graph-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1 L 8 5 L 0 9" fill="none" stroke="context-stroke" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </marker>
        </defs>
        {graph.edges.map((edge, i) => {
          const a = byId.get(edge.from)!;
          const b = byId.get(edge.to)!;
          const x1 = a.x + a.w / 2;
          const y1 = a.y + a.h;
          const x2 = b.x + b.w / 2;
          const y2 = b.y - 4;
          const bend = (y2 - y1) / 2;
          const d = `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
          const lit = hovered && (edge.from === hovered || edge.to === hovered);
          const dim = hovered && !lit;
          return (
            <g key={`${edge.from}->${edge.to}`} className={`graph__edge graph__edge--${edge.kind}${lit ? ' graph__edge--lit' : ''}${dim ? ' graph__edge--dim' : ''}`}>
              <motion.path
                d={d}
                markerEnd="url(#graph-arrow)"
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ duration: 0.55, delay: Math.min(0.1 + i * 0.03, 0.4), ease: [0.23, 1, 0.32, 1] }}
              />
              {edge.label ? (
                <text x={(x1 + x2) / 2 + 8} y={(y1 + y2) / 2} className="graph__label">
                  {edge.label}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      {graph.nodes.map((node, i) => (
        <motion.button
          key={node.id}
          className={`graph__node graph__node--${node.kind}${node.id === startup ? ' graph__node--startup' : ''}${connected(node.id) ? '' : ' graph__node--dim'}`}
          style={{ left: node.x, top: node.y, width: node.w, height: node.h }}
          initial={{ opacity: 0, y: 10, scale: 0.94 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: 'spring', bounce: 0.15, duration: 0.5, delay: Math.min(i * 0.04, 0.3) }}
          onPointerEnter={() => onHover?.(node.id)}
          onPointerLeave={() => onHover?.(null)}
          onClick={() => onOpen?.(node)}
        >
          <span className="graph__icon">
            <Icon icon={node.kind === 'target' ? typeIcon(node.type ?? '') : PackageIcon} size={node.kind === 'target' ? 17 : 14} />
          </span>
          <span className="graph__text">
            <span className="graph__name">{node.label}</span>
            <span className="graph__detail">{node.detail}</span>
          </span>
        </motion.button>
      ))}
    </>
  );
}
