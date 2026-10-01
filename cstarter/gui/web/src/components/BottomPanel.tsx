// Le panneau du bas : la sortie des opérations (MSBuild, git, CMake…), le terminal intégré
// et le programme qu'Exécuter a lancé, tous rendus par xterm.js. Sa
// poignée le redimensionne ; sans réglage, sa hauteur suit celle de la fenêtre.

import { useEffect, useRef } from 'react';
import { motion } from 'motion/react';
import { Terminal as XTerminal, type ITheme } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { ArrowDown01Icon, Delete02Icon, RefreshIcon, StopIcon } from '@hugeicons/core-free-icons';
import { stopProgram } from '../lib/actions';
import { call } from '../lib/bridge';
import { t } from '../lib/i18n';
import { output, program, terminal, type Log } from '../lib/log';
import { panelHeight, setState, useStore, useWindowHeight, type PanelTab } from '../lib/store';
import { Button, Segmented } from './ui';
import './BottomPanel.css';

const THEME: ITheme = {
  background: '#00000000',
  foreground: '#c9c9d3',
  cursor: '#b3b1ff',
  cursorAccent: '#09090b',
  selectionBackground: 'rgba(142, 140, 255, 0.32)',
  black: '#26262d',
  red: '#ff6b6b',
  green: '#3ddc97',
  yellow: '#f5b544',
  blue: '#7aa7ff',
  magenta: '#c7a2ff',
  cyan: '#5ec8ff',
  white: '#d6d6de',
  brightBlack: '#5c5c68',
  brightRed: '#ff8f8f',
  brightGreen: '#6ff0b6',
  brightYellow: '#ffd27a',
  brightBlue: '#9fc0ff',
  brightMagenta: '#dcc3ff',
  brightCyan: '#8fdcff',
  brightWhite: '#ffffff'
};

// Ce qu'un onglet interactif fait de la frappe et de sa taille : le terminal démarre PowerShell à sa
// première ouverture, le programme est déjà lancé.
interface Wiring {
  input: (data: string) => void;
  resize: (cols: number, rows: number) => void;
  start?: () => Promise<unknown>;
}

const TERMINAL: Wiring = {
  input: data => call('terminal_input', data),
  resize: (cols, rows) => call('terminal_resize', cols, rows),
  start: () => call('terminal_open', terminal.grid.cols, terminal.grid.rows).then(() => setState({ terminalAlive: true }))
};

const PROGRAM: Wiring = {
  input: data => call('program_input', data),
  resize: (cols, rows) => call('program_resize', cols, rows)
};

export default function BottomPanel() {
  const panel = useStore(s => s.panel);
  const alive = useStore(s => s.terminalAlive);
  const running = useStore(s => s.program !== null && s.program.code === null);
  const hasProgram = useStore(s => s.program !== null);
  const height = panelHeight(panel.height, useWindowHeight());
  const dragging = useRef<{ y: number; height: number } | null>(null);

  const setTab = (tab: PanelTab) => setState(s => ({ panel: { ...s.panel, tab, open: true } }));
  const tabs: { value: PanelTab; label: string }[] = [
    { value: 'output', label: t('Sortie', 'Output') },
    { value: 'terminal', label: 'Terminal' },
    ...(hasProgram ? [{ value: 'program' as PanelTab, label: t('Programme', 'Program') }] : [])
  ];

  return (
    <motion.section className="panel" initial={false} animate={{ height: panel.open ? height : 38 }} transition={dragging.current ? { duration: 0 } : { type: 'spring', bounce: 0, duration: 0.4 }}>
      <div
        className="panel__grip"
        onPointerDown={event => {
          if (!panel.open) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          dragging.current = { y: event.clientY, height };
        }}
        onPointerMove={event => {
          if (!dragging.current) return;
          const next = Math.round(dragging.current.height - (event.clientY - dragging.current.y));
          setState(s => ({ panel: { ...s.panel, height: panelHeight(next, window.innerHeight) } }));
        }}
        onPointerUp={() => (dragging.current = null)}
        onPointerCancel={() => (dragging.current = null)}
      />
      <header className="panel__head">
        <Segmented size="sm" tabs value={panel.tab} onChange={setTab} items={tabs} />
        <div className="panel__tools">
          {panel.open && panel.tab === 'output' ? (
            <Button tone="ghost" size="sm" icon={Delete02Icon} onClick={() => output.clear()}>
              {t('Effacer', 'Clear')}
            </Button>
          ) : null}
          {panel.open && panel.tab === 'program' && running ? (
            <Button tone="ghost" size="sm" icon={StopIcon} onClick={stopProgram}>
              {t('Arrêter', 'Stop')}
            </Button>
          ) : null}
          <Button
            tone="ghost"
            size="sm"
            icon={ArrowDown01Icon}
            className={`panel__fold${panel.open ? '' : ' panel__fold--closed'}`}
            onClick={() => setState(s => ({ panel: { ...s.panel, open: !s.panel.open } }))}
            title={panel.open ? t('Replier', 'Collapse') : t('Déplier', 'Expand')}
          />
        </div>
      </header>
      <div className="panel__body">
        <XTerm log={output} visible={panel.open && panel.tab === 'output'} />
        <XTerm log={terminal} visible={panel.open && panel.tab === 'terminal'} wiring={TERMINAL} />
        <XTerm log={program} visible={panel.open && panel.tab === 'program'} wiring={PROGRAM} />
        {panel.open && panel.tab === 'terminal' && !alive ? <RestartTerminal /> : null}
      </div>
    </motion.section>
  );
}

function RestartTerminal() {
  return (
    <div className="panel__restart">
      <Button tone="secondary" size="sm" icon={RefreshIcon} onClick={() => window.dispatchEvent(new Event('cstarter-open-terminal'))}>
        {t('Relancer le terminal', 'Restart the terminal')}
      </Button>
    </div>
  );
}

function XTerm({ log, visible, wiring }: { log: Log; visible: boolean; wiring?: Wiring }) {
  const host = useRef<HTMLDivElement>(null);
  const state = useRef<{ term: XTerminal; fit: FitAddon; started: boolean } | null>(null);

  useEffect(() => {
    const term = new XTerminal({
      fontFamily: "'Cascadia Mono', 'Cascadia Code', Consolas, monospace",
      fontSize: 12.5,
      fontWeight: '300',
      fontWeightBold: '600',
      lineHeight: 1.3,
      letterSpacing: 0,
      theme: THEME,
      allowTransparency: true,
      convertEol: !wiring,
      cursorBlink: Boolean(wiring),
      cursorStyle: 'bar',
      disableStdin: !wiring,
      scrollback: 20000,
      smoothScrollDuration: 90
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host.current!);
    state.current = { term, fit, started: !wiring?.start };
    log.attach(
      text => term.write(text),
      () => term.reset()
    );
    const open = () => start(true);
    if (wiring) {
      term.onData(data => wiring.input(data));
      term.onResize(({ cols, rows }) => {
        log.grid = { cols, rows };
        wiring.resize(cols, rows);
      });
      if (wiring.start) window.addEventListener('cstarter-open-terminal', open);
    }
    return () => {
      log.detach();
      window.removeEventListener('cstarter-open-terminal', open);
      term.dispose();
    };
  }, []);

  // Ajuster la grille pendant que le panneau s'ouvre ou se replie la réduirait à une ligne : la
  // pseudo-console se redessinerait et perdrait son écran.
  const fit = () => {
    const current = state.current;
    if (current && host.current && host.current.clientWidth > 0 && host.current.clientHeight >= 90) {
      current.fit.fit();
      log.grid = { cols: current.term.cols, rows: current.term.rows };
    }
  };

  const start = (again = false) => {
    const current = state.current;
    if (!current || !wiring?.start || (current.started && !again)) return;
    current.started = true;
    fit();
    wiring.start().catch(error => current.term.write(`\x1b[31m${error.message}\x1b[0m\r\n`));
    current.term.focus();
  };

  useEffect(() => {
    const current = state.current;
    if (!visible || !current || !host.current) return;
    const observer = new ResizeObserver(fit);
    observer.observe(host.current);
    const timer = setTimeout(() => {
      fit();
      if (wiring) {
        if (!current.started) start();
        else current.term.focus();
      }
    }, 260);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, [visible]);

  return <div ref={host} className={`xterm-host${visible ? '' : ' xterm-host--hidden'}`} />;
}
