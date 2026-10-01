// La sortie, le terminal et le programme lancé gardent leur texte même quand leur onglet n'est pas
// affiché : l'onglet le rejoue en s'ouvrant, puis reçoit la suite. Les vider vide aussi l'onglet.

const LIMIT = 2_000_000;

export class Log {
  private chunks: string[] = [];
  private size = 0;
  private sink: ((text: string) => void) | null = null;
  private reset: (() => void) | null = null;
  // La grille du terminal qui l'affiche, que la pseudo-console du programme reprend.
  grid = { cols: 120, rows: 30 };

  write(text: string): void {
    this.chunks.push(text);
    this.size += text.length;
    while (this.size > LIMIT && this.chunks.length > 1) this.size -= this.chunks.shift()!.length;
    this.sink?.(text);
  }

  section(title: string): void {
    this.write(`\r\n\x1b[38;2;142;140;255m●\x1b[0m \x1b[1m${title}\x1b[0m\r\n`);
  }

  attach(sink: (text: string) => void, reset: () => void): void {
    this.sink = sink;
    this.reset = reset;
    sink(this.chunks.join(''));
  }

  detach(): void {
    this.sink = null;
    this.reset = null;
  }

  clear(): void {
    this.chunks = [];
    this.size = 0;
    this.reset?.();
  }
}

export const output = new Log();
export const terminal = new Log();
export const program = new Log();
