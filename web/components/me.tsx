"use client";

import { createContext, useContext } from "react";
import type { Me } from "@/lib/api";

export const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);
