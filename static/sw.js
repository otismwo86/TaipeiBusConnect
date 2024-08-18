self.addEventListener("push", (event) => {
    const data = event.data.json();
    const clickAction = data.data?.click_action || '/'; 
    const { title, body, icon } = data.notification;

    event.waitUntil(
        self.registration.showNotification(title, {
            body: body,
            icon: icon,
            data: {
                url: clickAction
            }
        })
    );
});

self.addEventListener("notificationclick", (event) => {
    const url = event.notification.data.url || '/';
    //console.log("Notification click detected, opening URL:", url);
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
            for (let client of windowClients) {
                if (client.url === url && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(url);
            }
        })
    );
});