// تعريفات أنواع مختصرة لـ React 19 لأن @types/react غير مثبت في بيئة البناء.
// تغطي الـAPI المستخدم في المشروع فقط، وتسمح لـ tsc بفحص منطق التطبيق نفسه.
declare module "react" {
  export type ReactNode = ReactElement | string | number | boolean | null | undefined | ReactNode[];
  export interface ReactElement { type: unknown; props: unknown; key: string | null }
  export type SetState<T> = (v: T | ((prev: T) => T)) => void;
  export function useState<T>(init: T | (() => T)): [T, SetState<T>];
  export function useEffect(fn: () => void | (() => void), deps?: readonly unknown[]): void;
  export function useLayoutEffect(fn: () => void | (() => void), deps?: readonly unknown[]): void;
  export function useMemo<T>(fn: () => T, deps: readonly unknown[]): T;
  export function useCallback<T extends (...a: never[]) => unknown>(fn: T, deps: readonly unknown[]): T;
  export function useRef<T>(init: T): { current: T };
  export function useId(): string;
  export const Fragment: unique symbol;
  export const StrictMode: (p: { children?: ReactNode }) => ReactElement;
  export interface ChangeEvent<T = HTMLInputElement> { target: T }
  export interface FormEvent { preventDefault(): void }
  export interface MouseEvent<T = Element> { currentTarget: T; clientX: number; clientY: number; stopPropagation(): void }
  export interface KeyboardEvent { key: string; preventDefault(): void }
  export interface CSSProperties { [k: string]: string | number | undefined }
}
declare module "react/jsx-runtime" {
  export const jsx: unknown; export const jsxs: unknown; export const Fragment: unknown;
}
declare module "react-dom/client" {
  import type { ReactNode } from "react";
  export function createRoot(el: Element): { render(n: ReactNode): void };
}
declare namespace JSX {
  type Element = import("react").ReactElement;
  interface IntrinsicAttributes { key?: string | number }
  // أحداث DOM المستخدمة؛ target عام لأن الشِّم لا يميّز نوع العنصر
  interface DomEvent { target: any; currentTarget: any; key: string; clientX: number; clientY: number; preventDefault(): void; stopPropagation(): void } // eslint-disable-line @typescript-eslint/no-explicit-any
  interface IntrinsicProps {
    [prop: string]: any; // eslint-disable-line @typescript-eslint/no-explicit-any
    onChange?: (e: DomEvent) => void; onClick?: (e: DomEvent) => void; onSubmit?: (e: DomEvent) => void;
    onKeyDown?: (e: DomEvent) => void; onMouseMove?: (e: DomEvent) => void; onMouseEnter?: (e: DomEvent) => void; onMouseLeave?: (e: DomEvent) => void;
  }
  interface IntrinsicElements { [elemName: string]: IntrinsicProps }
  interface ElementChildrenAttribute { children: unknown }
}
