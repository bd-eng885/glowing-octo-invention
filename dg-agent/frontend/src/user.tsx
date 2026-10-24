import { createContext, useContext } from "react";

export type User = { id: number; email: string; full_name: string; role: string; qualification: string; permissions: string[] };
export const UserCtx = createContext<User | null>(null);
export const useUser = () => useContext(UserCtx);
