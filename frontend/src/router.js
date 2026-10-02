import { createRouter, createWebHistory } from "vue-router"

import { bootSession, session } from "./data/session.js"

import BulkProgress from "./pages/BulkProgress.vue"
import Home from "./pages/Home.vue"
import Login from "./pages/Login.vue"
import NewTransfer from "./pages/NewTransfer.vue"
import NotFound from "./pages/NotFound.vue"
import TransferDetail from "./pages/TransferDetail.vue"
import Transfers from "./pages/Transfers.vue"

// Every top-level path here needs a website_route_rules entry in hooks.py, or
// a hard refresh on it returns 404 (there is deliberately no catch-all).
export const router = createRouter({
  history: createWebHistory("/staff/"),
  routes: [
    { path: "/login", name: "login", component: Login },
    // Home is /staff/home, not /staff/: nginx 301s "/staff/" to "/staff", which is
    // OUTSIDE the PWA scope "/staff/" (Android then shows a browser bar / won't install).
    { path: "/", redirect: "/home" },
    { path: "/home", name: "home", component: Home, meta: { auth: true } },
    { path: "/transfer", name: "transfer", component: NewTransfer, meta: { auth: true } },
    { path: "/transfers", name: "transfers", component: Transfers, meta: { auth: true } },
    { path: "/t/:name", name: "detail", component: TransferDetail, props: true, meta: { auth: true } },
    { path: "/bulk/:ref_", name: "bulk", component: BulkProgress, props: true, meta: { auth: true } },
    { path: "/:pathMatch(.*)*", name: "notfound", component: NotFound },
  ],
})

router.beforeEach(async (to) => {
  if (!session.booted) await bootSession()
  const guest = !session.user || session.user === "Guest"
  if (to.meta.auth && guest) return { name: "login" }
  if (to.name === "login" && !guest) return { name: "home" }
  return true
})
