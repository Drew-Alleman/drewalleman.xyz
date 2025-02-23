---
layout: post
title: "Creating a High-Performance C++ Port Scanner with Boost"
description: "Learn how to build a fast, asynchronous port scanner in C++ using Boost's async_connect function. Complete guide with code examples and performance analysis."
date: 2025-02-20 22:38:22 -0700
categories: [coding, c++, hacking]
tags: [cpp, networking, boost, async, port-scanner, security-tools]
image: /assets/images/boost-library.png
image_alt: "Boost C++ Libraries Logo showing asynchronous programming concepts"
author: Drew Alleman
last_modified_at: 2025-02-20 22:38:22 -0700
---
## Intro 
I wanted to sharpen my C++ networking skills and thought of no better project then a asynchronous port scanner. In this blog post, I'll walk you through some of the key components of the code responsible for handling asynchronous connections. To see the whole codebase please click [here](https://github.com/Drew-Alleman/bps). 
### Why Boost?
![Async vs Sync Programming](/static/images/asynchronous-vs-synchronous-programming.png)
By leveraging Boost's [async_connect](https://www.boost.org/doc/libs/1_87_0/doc/html/boost_asio/reference/async_connect.html) function, we can make non-blocking network requests through asynchronous programming. This approach enables the port scanner to handle multiple connections concurrently without getting bogged down by slow, blocking calls.
#### Synchronous 
The code below is a standard implementation of a port scanner using `winsocks2`. The problem is that even with multithreading, this synchronous approach is inefficient—it still takes <b>10+ minutes</b> to scan the port range from 1 to 65535 on localhost. 
```c++
bool Scanner::isPortOpen(int port) {
    /*
    @brief Checks to see if the provided port is open on
    the loaded target.

    @param port A port number between 1 and 65535
    @return True if the port is open, otherwise False
    */
    
	// Create a socket that is connected to the target and port
    std::tuple<SOCKET, int> result = createConnectedSocket(port);
    SOCKET connectionSocket = std::get<0>(result);
    int iResult = std::get<1>(result);
    // If we couldnt connect then the port is closed or filtered
    if (iResult == SOCKET_ERROR) {
        return false;
    }
    iResult = closesocket(connectionSocket);
    if (iResult == SOCKET_ERROR)
        wprintf(L"closesocket function failed with error: %ld\n", WSAGetLastError());
    return true;
}
```
## Getting Started With Boost
To get started with boost  we first need to define a [`io_context`](https://live.boost.org/doc/libs/1_84_0/doc/html/boost_asio/reference/io_context.html). I will be making this an attribute of the `Scanner` class.  The `io_context` is responsible for the actual calling, and handling of our asynchronous events in the event loop.

```c++
class Scanner {
	public:
	    io_context ctx;
}
```
### Breaking Down The determinePortStatus() Function
In this section I will be creating a function that asynchronously determines the port status of the provided port on a target. The result is recorded in a dictionary called `scanResults`. To ensure thread-safe modifications to `scanResults`, a mutex is used.

```c++
// Enum to represent the state of a port `
enum class PortState {
    Open,
    Closed,
    Filtered,
    Unknown
};

// Structure to store port information
struct PortInfo {
    int port;
    PortState status;
};

// Scanner class responsible for scanning ports
class Scanner {
	public:
	    io_context ctx;
	    std::unordered_map<std::string, std::vector<PortInfo>> scanResults;
	    std::mutex portsMutex;
}
```

We can then use the following function to update the results.

```c++
void Scanner::updateDictionary(Target target, PortInfo portInfo) {
    /*
    * @brief A thread-safe way to update the `scanResults` vector.
    *
    * Uses a mutex to ensure no other thread is writing to the scanResults before attempting 
    * to read/write to it.
    *
    * @param[in] The target you want to update
    * @param[in] PortInfo struct holding the port and the status
    */
    std::unique_lock<std::mutex> lock(portsMutex);
    // Ensure there is an entry for the target's pretty name.
    std::vector<PortInfo>& portVec = scanResults[target.prettyName];

    bool alreadyExists = std::any_of(portVec.begin(), portVec.end(),
        [port = portInfo.port](const PortInfo& info) { return info.port == port; });

    // If we already have the port recorded for the target then return.
    if (alreadyExists) {
        logger->debug("[Scanner::updateDictionary] Port: {} on host: {} is already recorded", portInfo.port, target.prettyName);
        return;
    }

    portVec.push_back({ portInfo.port, portInfo.status });
    logger->debug("[Scanner::updateDictionary] Added port: {} to host: {} dictionary", portInfo.port, target.prettyName);
    logger->info("Discovered {} port {}/tcp on {}", state_to_string(portInfo.status), portInfo.port, target.prettyName);
}
```
#### Setting Up the Environment
The function starts by creating a **[strand](https://beta.boost.org/doc/libs/1_45_0/doc/html/boost_asio/reference/io_service__strand.html)** from the global event loop. A strand guarantees that all callbacks associated with it are executed serially, ensuring thread safety when multiple asynchronous operations are involved.

```c++
boost::asio::strand strand = boost::asio::make_strand(ctx);
```
#### Resource Initialization
Next, several shared resources are initialized:
- An **atomic boolean flag** (`completed`) to indicate whether the port scan has finished.
- A **TCP socket** for the connection attempt.
- A **timer** to enforce a timeout in case the connection takes too long.

```c++
auto completed = std::make_shared<std::atomic_bool>(false);
auto socket = std::make_shared<boost::asio::ip::tcp::socket>(ctx); 
auto timer = std::make_shared<boost::asio::steady_timer>(ctx);
```
#### Configuring the Endpoint and Timer
A TCP endpoint is created using the target's IP address and the specific port number to be scanned. The timer is then configured to expire after a preset timeout period (for example, 3 seconds).

```c++
boost::asio::ip::tcp::endpoint endpoint(target.address, port);
timer->expires_after(std::chrono::seconds(3));
```

#### Initiating the Asynchronous Connection
An asynchronous connection attempt is sent to the event loop using the socket's `async_connect` method. This method is bound to the strand to ensure serial execution of the callback. The lambda function captures all necessary variables and will be invoked once the connection attempt either succeeds or fails.

```c++
socket->async_connect(
    endpoint, // The IP address and port we are connecting to represented as a basic_socket
    boost::asio::bind_executor(
	    strand,        // The strand we defined earlier
        [this, target] // Variables captured to be available in the callback.
        (const boost::system::error_code& ec) { // The error code provided upon completion.
            // This block is the callback executed once the async connect completes.
            std::cout << "Anything in here will get printed when this async connect is called!" << std::endl;
        } // Callback ends
    )
);

```

Now that you understand the parameters of `async_connect`, let's break down some of the key features in the code:

- **Atomic Completion Check:** An atomic exchange marks the operation as complete, ensuring that cleanup routines are executed only once, even if multiple callbacks are triggered.

- **Timer Cancellation:** Once the connection attempt finishes, the timer is canceled to prevent its timeout handler from running unnecessarily.

- **Socket State Verification:** After the connection, the socket’s state is examined. A successful connection results in the port being marked as open, while any failure triggers the appropriate error-handling routine.

```c++
socket->async_connect(endpoint, boost::asio::bind_executor(strand,
    [this, target, port, socket, timer, retries, strand, completed](const boost::system::error_code& ec) {
    // This is the callback `function`
        boost::system::error_code ignore;
        timer->cancel(ignore);
        bool isPortOpen = socket->is_open();
        socket->close();
        if (!ec && isPortOpen) {
            PortInfo portInfo = PortInfo(port, PortState::Open);
            updateDictionary(target, portInfo);
        }
        else {
            handleSocketError(strand, ec, port, target, retries);
        }
    } // Callback ends
));

```

#### Handling Timeouts
Parallel to the connection attempt, the timer is set up to wait asynchronously. If the timer expires before the connection completes—and if the operation hasn't been marked complete—the timer’s callback will cancel the socket, ensuring that lingering connection attempts do not hold up the scanning process.

```c++
timer->async_wait([socket, completed](const boost::system::error_code& ec) {
    if (!ec && !completed->load()) {
        socket->cancel();
    }
});
```
#### Complete determinePortStatus() Code
```c++
void Scanner::determinePortStatus(Target target, int port, int retries) {
    /**
     * @brief Attempts to determine if a given port on a target is open.
     *
     * @param target The target host to scan.
     * @param port The port number to test.
     * @param retries The allowed number of retry attempts if connection fails.
     */
    boost::asio::strand strand = boost::asio::make_strand(ctx);
    auto completed = std::make_shared<std::atomic_bool>(false);
    auto socket = std::make_shared<boost::asio::ip::tcp::socket>(ctx);
    auto timer = std::make_shared<boost::asio::steady_timer>(ctx);
    boost::asio::ip::tcp::endpoint endpoint(target.address, port);
    timer->expires_after(std::chrono::seconds(timeout));

    socket->async_connect(endpoint, boost::asio::bind_executor(strand,
        [this, target, port, socket, timer, retries, strand, completed](const boost::system::error_code& ec) {
            if (!completed->exchange(true)) {
                activeConnections.fetch_sub(1);
            }
            boost::system::error_code ignore;
            timer->cancel(ignore);
            bool isPortOpen = socket->is_open();
            socket->close();
            if (!ec && isPortOpen) {
                PortInfo portInfo = PortInfo(port, PortState::Open);
                updateDictionary(target, portInfo);
            }
            else {
                handleSocketError(strand, ec, port, target, retries);
            }
        }
    ));

    timer->async_wait([socket, completed](const boost::system::error_code& ec) {
        if (!ec && !completed->load()) {
            socket->cancel();
        }
    });
}
```

### Calling determinePortStatus()
Currently none of the code above will actually send out the networking request. To do that we need to use `ctx.run()` to start the event loop.  We can use the following code segment to start posting the operations to the event loop

```c++
for (Target& target : targets) {
	for (int port = startPort; port <= endPort; ++port) {
		ctx.post([this, target, port]() {
			determinePortStatus(target, port, 3);
			});
	}
}
```

Then we can use the following code to start the async connections, the nice thing about `ctx.run()` is that its thread safe, meaning we can utilize multithreading to launch multiple nonblocking connections at once. 

```c++
unsigned int threadCount = std::max(1u, std::thread::hardware_concurrency());
if (logger) {
	logger->debug("[Scanner::scan] Using {} threads to run the ctx context", threadCount);
}
std::vector<std::thread> threads;
for (unsigned int i = 0; i < threadCount; ++i) {
	threads.emplace_back([this]() { ctx.run(); });
}
for (Target& target : targets) {
	for (int port = startPort; port <= endPort; ++port) {
		ctx.post([this, target, port]() {
			determinePortStatus(target, port, 3);
			});
	}
}
```
### Conclusion
In conclusion, leveraging Boost's asynchronous capabilities has transformed our port scanner into a highly efficient and responsive tool. By using `async_connect` alongside atomic flags, strands for thread safety, and timers for managing timeouts, we’ve been able to handle multiple connections concurrently without blocking the application. 

```
C:\Users\Drew\Desktop\bps\x64\Release> .\bps.exe -t 192.168.0.1 -e 65355
starting BPS (https://github.com/Drew-Alleman/bps)
BPS scan report for 192.168.0.1
PORT      STATE       SERVICE GUESS
53/tcp    FILTERED    DNS
80/tcp    OPEN        HTTP
443/tcp   OPEN        HTTPS
21515/tcp OPEN        Unknown
49152/tcp OPEN        Unknown

BPS done: 1 IP address scanned in 25.22 seconds
```