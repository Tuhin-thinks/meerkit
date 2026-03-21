import { createApp } from "vue";
import { createPinia } from "pinia";
import { VueQueryPlugin, QueryClient } from "@tanstack/vue-query";
import App from "./App.vue";
import router from "./router";
import "./style.css";

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            // Treat server data as fresh for 5 minutes; never auto-refetch on window focus
            staleTime: 5 * 60 * 1000,
            gcTime: 60 * 60 * 1000,
            refetchOnWindowFocus: false,
            retry: 1,
        },
    },
});

const app = createApp(App);
app.use(createPinia());
app.use(VueQueryPlugin, { queryClient });
app.use(router);
app.mount("#app");
