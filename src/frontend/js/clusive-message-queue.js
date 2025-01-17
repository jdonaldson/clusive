/* global cisl, clusive, fluid_3_0_0, gpii, DJANGO_STATIC_ROOT, DJANGO_CSRF_TOKEN */

(function(fluid) {
    'use strict';

    fluid.defaults("clusive.messageQueue", {       
        gradeNames: ["fluid.component"],    
        members: {
            queue: [],
            sendingQueue: {}
        },
        config: {
            // Interval for trying to flush queue
            flushInterval: "@expand:{that}.getFlushInterval(15000)",
            // Namespace for local storage key
            localStorageKey: "clusive.messageQueue.queue"
        },
        events: {
            queueShouldFlush: null,
            queueFlushStarting: null,
            queueFlushSuccess: null,
            queueFlushFailure: null,
            syncedToLocalStorage: null        
        },
        listeners: {
            "onCreate.syncFromLocalStorage": {
                func: "clusive.messageQueue.syncFromLocalStorage",
                args: ["{that}"]                
            },
            "onCreate.setFlushInterval": {
                funcName: "{that}.setFlushInterval"                
            },
            "queueShouldFlush.flushQueue": {
                funcName: "{that}.flush"
            },
            "queueFlushSuccess.clearsendingQueue": {
                func: "{that}.clearsendingQueue",                
            },
            "queueFlushFailure.restoreQueue": {
                func: "{that}.restoreQueue"                            
            },            

        },
        invokers: {
            add: {
                funcName: "clusive.messageQueue.addMessage",
                args: ["{that}", "{arguments}.0"]
            },
            clearsendingQueue: {
                funcName: "clusive.messageQueue.clearsendingQueue",
                args: ["{that}"]                
            },
            restoreQueue: {
                funcName: "clusive.messageQueue.restoreQueue",
                args: ["{that}"]                
            },            
            getMessages: {
                funcName: "clusive.messageQueue.getMessages",
                args: ["{that}"]
            },            
            wrapMessage: {
                funcName: "clusive.messageQueue.wrapMessage",
                args: ["{arguments}.0"]
            },
            flush: {
                funcName: "clusive.messageQueue.flushQueue",
                args: ["{that}", "{that}.setupQueueFlushPromise"]
            },
            getFlushInterval: {
                funcName: "clusive.messageQueue.getFlushInterval",
                args: ["{arguments}.0"]
            },
            setupQueueFlushPromise: {
                funcName: "clusive.messageQueue.setupQueueFlushPromise",
                args: ["{that}", "{arguments}.0", "{that}.handleQueueFlushPromiseSuccess", "{that}.handleQueueFlushPromiseFailure"]
            },
            handleQueueFlushPromiseSuccess: {
                funcName: "clusive.messageQueue.handleQueueFlushPromiseSuccess",
                args: ["{that}", "{arguments}.0"]
            },
            handleQueueFlushPromiseFailure: {
                funcName: "clusive.messageQueue.handleQueueFlushPromiseFailure",
                args: ["{that}", "{arguments}.0"]
            },
            flushQueueImpl: {
                funcName: "fluid.notImplemented",
                args: ["{that}", "{arguments}.0"]
            },
            setFlushInterval: {
                funcName: "clusive.messageQueue.setFlushInterval",
                args: ["{that}"]
            },
            syncFromLocalStorage: {
                funcName: "clusive.messageQueue.syncFromLocalStorage",
                args: ["{that}"]
            },
            syncToLocalStorage: {
                funcName: "clusive.messageQueue.syncToLocalStorage",
                args: ["{that}"]
            }            
        },
    });    

    clusive.messageQueue.getFlushInterval = function (defaultInterval) {
        console.log("clusive.messageQueue.getFlushInterval", defaultInterval);
        return defaultInterval;
    }

    clusive.messageQueue.flushQueue = function (that, setupPromiseFunc) {
        // Don't flush if we have an empty queue
        if(that.queue.length > 0 ) {                    
            that.sendingQueue.timestamp = new Date().toISOString();
            that.sendingQueue.messages = [].concat(that.queue);
            that.queue = [];
            that.syncToLocalStorage();
            var promise = fluid.promise();
            that.events.queueFlushStarting.fire();     
            setupPromiseFunc(promise);
            return that.flushQueueImpl(promise);            
        }
    }

    clusive.messageQueue.setupQueueFlushPromise = function (that, promise, successFunc, failureFunc) {        
        promise.then(
            function(value) {
                successFunc(value)
            },
            function(error) {
                failureFunc(error)
            })
    }

    clusive.messageQueue.handleQueueFlushPromiseSuccess = function (that, value) {
        that.events.queueFlushSuccess.fire(value);
    }

    clusive.messageQueue.handleQueueFlushPromiseFailure = function (that, error) {
        that.events.queueFlushFailure.fire(error);
    }

    clusive.messageQueue.setFlushInterval = function (that) {
        var flushInterval = that.options.config.flushInterval;
        setInterval(function () {
            that.events.queueShouldFlush.fire();
        }, flushInterval)
    }

    // A message is any POJO
    clusive.messageQueue.addMessage = function(that, message) {  
        // Make sure we're synced up with any changes in local storage
        // that other components might have caused
        that.syncFromLocalStorage();      
        var newQueue = fluid.get(that, "queue");        
        newQueue.push(that.wrapMessage(message));
        that.queue = newQueue;
        that.syncToLocalStorage();
    }

    // Get the current queue of messages
    clusive.messageQueue.getMessages = function(that) {
        that.syncFromLocalStorage();
        return that.queue;
    }

    clusive.messageQueue.wrapMessage = function(message) {
        var timestamp = new Date().toISOString();
        var wrappedMessage = {
            content: message,            
            timestamp: timestamp
        };
        return wrappedMessage;
    }

    clusive.messageQueue.syncFromLocalStorage = function(that) {            
        var messagesInLocalStorage = localStorage.getItem(that.options.config.localStorageKey);                
        if(messagesInLocalStorage) {             
            var parsedMessages = JSON.parse(messagesInLocalStorage);  
            that.queue = parsedMessages;                      
        }
    }

    clusive.messageQueue.syncToLocalStorage = function(that) {           
        localStorage.setItem(that.options.config.localStorageKey, JSON.stringify(that.queue));
        that.events.syncedToLocalStorage.fire();
    }

    clusive.messageQueue.clearsendingQueue = function(that) { 
        that.sendingQueue = {};                
    }

    clusive.messageQueue.restoreQueue = function(that) {         
        that.queue = that.sendingQueue.messages.concat(that.queue);
        that.sendingQueue = {};
        that.syncToLocalStorage();        
    }

}(fluid_3_0_0));