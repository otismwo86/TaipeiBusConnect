// notifications.js

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import { getMessaging, getToken } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-messaging.js";

// Your web app's Firebase configuration
const firebaseConfig = {
    apiKey: "AIzaSyA-jKul-vcdLDSKKsqvidozpwFR7nSlg4M",
    authDomain: "busconncet.firebaseapp.com",
    projectId: "busconncet",
    storageBucket: "busconncet.appspot.com",
    messagingSenderId: "995952558379",
    appId: "1:995952558379:web:52d8e5669eb808639c856e",
    measurementId: "G-FZ2J5TNPS3"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const messaging = getMessaging(app);

let currentToken = null;
// Register the service worker and get the token
navigator.serviceWorker.register("/static/sw.js").then(registration => {
    return getToken(messaging, { 
        serviceWorkerRegistration: registration,
        vapidKey: 'BLm85xwe-izyf833HKW-yTwTzjMwvdGamD8uY6D_KR1BHz6EUrgfDKy_U1NNdHAIxk8h9fhsKc55-9kY31L2CWM'
    });
}).then(token => {
    if (token) {
        currentToken = token;
        //console.log(token)
    } else {
        console.log('No registration token available. Request permission to generate one.');
    }
}).catch(err => {
    console.log('An error occurred while retrieving token. ', err);
});

export function requestNotificationPermission() {
    Notification.requestPermission().then(permission => {
        if (permission === 'granted') {
        console.log('Notification permission granted.');
        } else {
            console.log('Notification permission denied.');
        }
    }).catch(err => {
        console.log('An error occurred while requesting notification permission.', err);
    });
}

export function triggerTestNotification() {
    const title = "您已成功設定公車提醒通知。";
    const body = "可以在會員功能中查詢";

    if (Notification.permission === 'granted') {
        new Notification(title, {
            body: body,
        });
    } else {
        console.log('Notification permission not granted.');
    }
}

export function sendNotification(nearestStopName, nearestStopTime) {
    const token = currentToken;  //Use the global token
    const urlParams1 = new URLSearchParams(window.location.search);
    const routeName1 = urlParams1.get('route_name');
    const title = `${routeName1}到站時間`;
    const body = `最近站牌為: ${nearestStopName}，到點時間: ${nearestStopTime}`;

    fetch('/api/notifications', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token, title, body }),
    })
    .then(response => response.json())
    .then(data => {
        //console.log('Success:', data);
    })
    .catch((error) => {
        //console.error('Error:', error);
    });
}

export function getCurrentToken() {
    return currentToken;
}