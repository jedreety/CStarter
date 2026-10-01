import { createRoot } from 'react-dom/client';
import '@xterm/xterm/css/xterm.css';
import './styles/theme.css';
import App from './App';
import { boot } from './lib/actions';

createRoot(document.getElementById('root')!).render(<App />);
boot();
