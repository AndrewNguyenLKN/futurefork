# Checklist tài khoản và điều kiện IBM Bob 2.0 Hackathon

File này lưu các yêu cầu hackathon và những thao tác người tham gia phải tự thực hiện. Claude/Bob có thể hỗ trợ kiểm tra kỹ thuật nhưng không được tự nhận rằng tài khoản, email hoặc submission đã hoàn tất nếu chưa có xác nhận của người dùng.

Nguồn chính thức:

- Trang sự kiện: <https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon>
- Hackathon Guide: <https://lablab-ibm-bob-2-hackathon-guide.s3.us.cloud-object-storage.appdomain.cloud/index.html>
- IBM Bob documentation: <https://bob.ibm.com/docs>

## Trạng thái hiện tại

- [x] Đã đăng ký sự kiện trên lablab.ai và trước đó đã thấy trạng thái Enrolled/Approved.
- [x] Đã tham gia Discord theo xác nhận của người dùng.
- [x] Đã tạo hoặc xác nhận IBMid và đăng nhập thành công vào IBM Bob.
- [x] Đã nhận/quyền truy cập tài khoản Bob do hackathon cấp; Admin Dashboard đã xác nhận team `ibm-hackathon-lablab`.
- [x] Đã cài và khởi chạy Bob IDE v2.2.0 (build `1.126.0+bob2.2.0.20260924155054`).
- [x] Đã đăng nhập Bob IDE bằng đúng IBMid.
- [x] Đã xác nhận đúng tài khoản hackathon Enterprise tại region `us-east` qua Admin Dashboard và quota 40 Bobcoins trong IDE.
- [x] Đã nhìn thấy 40 Bobcoins trong tài khoản hackathon; task thử dùng `0.384`, còn `39.616`.
- [x] Đã mở repository FutureFork bằng Bob IDE và hoàn tất task onboarding chỉ-đọc.
- [x] Đã chụp session consumption summary vào `bob_sessions/futurefork_task01_onboarding_summary.png`.
- [x] Đã xác định kênh chính thức trên Discord: `📢╭updates-ibm-bob-2-0-hackathon` và `💬╰participants-chat-ibm-bob-2-0-hackathon`.
- [ ] Đã tạo team một người trên lablab.ai để đủ điều kiện nộp submission.

Các dấu tích đầu tiên phản ánh thông tin đã xác nhận trong cuộc trao đổi. Người dùng cần tự xác nhận các mục còn lại trên tài khoản và máy của mình.

Kiểm tra trực tiếp ngày 26/09/2026 trên IBM Bob Admin Dashboard:

- Role: `User`; plan: `Enterprise`.
- Team: `ibm-hackathon-lablab`; region: `United States (East)`.
- Spending limit: `40 Bobcoins`; usage: `0`; remaining: `40`.
- Máy dùng Apple Silicon (`arm64`); cần bản Bob IDE **Mac ARM**.
- Đã tải và cài Bob IDE Mac ARM từ trang chính thức của IBM: `IBM-Bob-darwin-arm64-1.126.0+bob2.2.0.pkg`.
- SHA-256 của hai lượt tải độc lập đều là `4cd3159e8c420f47c5a322029689102f6f650aa8175b9a127f436830d2a07ca8`.
- Bob IDE đã khởi chạy; bỏ qua import cấu hình editor và migration chat v1 để giữ môi trường hackathon sạch. Đăng nhập IBMid trong IDE đã hoàn tất.
- Workspace `/Users/longkimnguyen/Documents/ChatGPT/IBM` đã được mở và đánh dấu trusted.
- Task onboarding chỉ-đọc đã hoàn tất với Task ID `5db93be60bab1c835d6a584a8e2f29c8`, dùng `0.384` Bobcoins; Bob không sửa file hoặc chạy lệnh.
- Bằng chứng phiên task: `bob_sessions/futurefork_task01_onboarding_summary.png` (PNG 2400 × 1600).

## Việc người dùng phải làm ngay, theo thứ tự

### 1. Kiểm tra email đăng ký hackathon

Xác định chính xác email đã dùng trên lablab.ai. Tất cả các bước IBMid và Bob phải dùng email này.

Không tạo IBMid bằng một email khác rồi hy vọng ghép tài khoản sau.

### 2. Tạo hoặc kiểm tra IBMid

Nếu chưa có IBMid cho email đăng ký, tạo tại liên kết **Create an IBMid** trong Hackathon Guide hoặc trang đăng nhập IBM.

Sau khi tạo:

- Xác minh email nếu IBM yêu cầu.
- Ghi nhớ phương thức đăng nhập, nhưng không lưu mật khẩu hay mã xác thực vào repository.
- Không đưa cookie, token hoặc ảnh chứa mã bảo mật cho Claude/Bob.

### 3. Tìm email mời IBM Bob của hackathon

Tìm trong Inbox, Promotions, Updates, Junk và Spam với từ khóa:

```text
IBM Bob
ibm-hackathon
team member
```

Email đúng sẽ nói rằng bạn được thêm làm team member vào một tài khoản có dạng `ibm-hackathon-xxxx`, thuộc Enterprise plan. Cụm “team member” là thuật ngữ cấp quyền tài khoản doanh nghiệp; nó không có nghĩa bạn đã được ghép vào một đội thi.

Mở email và hoàn tất thao tác chấp nhận lời mời. Nếu không thấy email dù đã dùng đúng địa chỉ đăng ký, hỏi ban tổ chức trên Discord và cung cấp email đăng ký; không đăng công khai mật khẩu hay token.

### 4. Cài hoặc nâng cấp Bob IDE

Bob IDE là bắt buộc; Bob Shell chỉ là tùy chọn.

- Nếu đang ở v1.0.3, nâng lên bản v2.0.x mới nhất.
- Nếu đang ở v2.0.0, nâng lên v2.0.2 hoặc mới hơn.
- Sau cài đặt, ghi lại version đang dùng.

Ban tổ chức thông báo v1.0.3 và v2.0.0 sẽ ngừng hoạt động từ 30/09/2026, vì vậy không dùng hai phiên bản này cho bài thi.

### 5. Đăng nhập Bob IDE bằng IBMid đúng

Trong Bob IDE:

1. Chọn **Log in to Bob**.
2. Hoàn tất IBMid authentication trong browser.
3. Mở **Settings → General**.
4. Kiểm tra tài khoản/instance đang chọn.

Nếu có nhiều tài khoản Bob, phải chọn instance hackathon tại region `us-east`. Hướng dẫn chính thức hiển thị tên dạng `ibm-coding-challenge-xxx` và ở phần đăng nhập dùng `ibm-coding-challenge-uat`; hãy chọn instance hackathon mà lời mời đã cấp, không dùng tài khoản cá nhân.

### 6. Kiểm tra 40 Bobcoins trước khi làm project

Trong **Settings → General** hoặc Bob Admin Dashboard:

- Xác nhận đang ở instance hackathon `us-east`.
- Xác nhận allocation là 40 Bobcoins hoặc mức ban tổ chức đã cấp.
- Chụp ảnh màn hình trạng thái nếu cần để xử lý hỗ trợ, nhưng không bắt buộc commit ảnh này.

Nếu không thấy Bobcoins, dừng sử dụng AI trên Bob và hỏi ban tổ chức trước; nếu tiếp tục trong tài khoản cá nhân, bạn có thể tiêu nhầm quota cá nhân.

### 7. Mở repository FutureFork trong Bob IDE

Mở thư mục:

```text
/Users/longkimnguyen/Documents/ChatGPT/IBM
```

Yêu cầu Bob đọc theo thứ tự:

```text
Read CLAUDE.md and docs/HACKATHON_SETUP_VI.md first. Then read README.md,
docs/PRODUCT_SPEC.md, docs/DEMO_STORY.md, docs/ARCHITECTURE.md, and BACKLOG.md.
Summarize the product contract, non-negotiable rules, current state, and the
first unchecked P0 task. Do not write code yet.
```

Kiểm tra bản tóm tắt của Bob trước khi giao task code. Bob phải hiểu rằng FutureFork so sánh bằng thực nghiệm, không phải tạo một “AI maintainability score”.

### 8. Chạy một task nhỏ để xác nhận Bob hoạt động

Task đầu tiên nên có phạm vi nhỏ, ví dụ yêu cầu Bob rà soát tài liệu và đề xuất cấu trúc scenario YAML. Chưa nên tiêu nhiều Bobcoins vào sáu experiment khi runner chưa hoạt động.

Ngay sau task thử:

1. Trong Bob IDE chat, mở **Tasks**.
2. Chọn đúng task và đúng workspace.
3. Nhấn vào task header để mở session consumption summary.
4. Chụp PNG.
5. Lưu vào `bob_sessions/` với tên rõ ràng.
6. Cập nhật `bob_sessions/INDEX.md`.

### 9. Thiết lập Discord để không bỏ lỡ thông báo

Tên kênh có thể thay đổi nên không tự suy đoán tên. Trong server:

1. Hoàn thành onboarding/role selection nếu Discord đang ẩn channel.
2. Tìm category hoặc channel có tên liên quan `IBM Bob 2.0`, `hackathon`, `announcements`, `Q&A`, `help` hoặc `support`.
3. Ưu tiên channel có bài ghim hoặc bài của organizer/moderator.
4. Chọn **Notification Settings → All Messages** cho channel thông báo chính thức.
5. Bật notification cho thread Q&A mà bạn tham gia.
6. Kiểm tra pinned messages và Events của server.

Nếu vẫn không xác định được channel, đăng một câu hỏi ngắn trong channel hỗ trợ chung: “Which channel is the official announcements and technical Q&A channel for the IBM Bob 2.0 Hackathon?”

Đã kiểm tra trực tiếp ngày 26/09/2026:

- Thông báo chính thức: `📢╭updates-ibm-bob-2-0-hackathon`.
- Thảo luận và Q&A: `💬╰participants-chat-ibm-bob-2-0-hackathon`.
- Người dùng yêu cầu Claude chỉ đọc; không gửi tin, reaction hoặc tương tác đại diện người dùng.
- Organizer xác nhận Bob IDE phải được thể hiện như một thành phần cốt lõi để đủ điều kiện chấm.
- Organizer xác nhận mỗi participant chỉ có 40 Bobcoins và không được cấp thêm khi dùng hết.
- Lablab bot xác nhận người thi solo vẫn phải tạo một team chỉ có chính mình trên trang sự kiện để nộp bài.

### 10. Tạo repository public, nhưng chưa public secrets

Submission cần repository code public. Trước khi push:

- Thêm license.
- Kiểm tra `.env`, token, credential, email cá nhân và URL nội bộ không bị commit.
- Chỉ dùng dữ liệu tổng hợp cho PocketCart.
- Giữ `bob_sessions/` trong repository cuối cùng.
- Không push artifact chứa environment dump hoặc credential.

Claude có thể chuẩn bị repository và kiểm tra secret pattern; người dùng phải tự đăng nhập Git provider và quyết định thời điểm public.

## Phân chia trách nhiệm

| Việc | Người dùng phải làm | Claude có thể làm | Bob IDE phải xuất hiện |
|---|---:|---:|---:|
| Đăng ký lablab.ai | Có | Kiểm tra trạng thái nếu được truy cập | Không |
| Tạo IBMid và xác thực email | Có | Hướng dẫn | Không |
| Chấp nhận email invite Bob | Có | Hướng dẫn | Không |
| Cài/đăng nhập/chọn instance | Có | Hướng dẫn và chẩn đoán | Có |
| Kiểm tra 40 Bobcoins | Có | Đọc ảnh/thông tin người dùng cung cấp | Có |
| Viết project code | Giám sát | Có thể hỗ trợ | Bob phải là thành phần cốt lõi |
| Chụp task summary | Có | Quản lý index/tên file | Có |
| Tạo repo public | Có quyền quyết định | Chuẩn bị nội dung và kiểm tra | Không bắt buộc |
| Nộp submission | Có | Chuẩn bị text/checklist | Bằng chứng Bob bắt buộc |

## Điều kiện hợp lệ phải luôn nhớ

- Prototype phải cải thiện một developer workflow cụ thể.
- Bob IDE phải là thành phần cốt lõi để đủ điều kiện chấm.
- Có thể dùng framework/công nghệ khác nhưng không được thay vai trò cốt lõi của Bob.
- Mỗi participant phải nộp tất cả Bob task-session summary screenshots liên quan.
- Folder phải có tên chính xác `bob_sessions`.
- Dữ liệu public chỉ dùng khi điều khoản cho phép commercial use và phải lưu danh sách nguồn.
- Không dùng client data, company confidential data, personal information hoặc dữ liệu social media.
- Mỗi participant có 40 Bobcoins; đạt 100% sẽ không được cấp thêm trong hackathon.
- Bob Shell và watsonx là tùy chọn.

## Mốc submission

- Event: 25–27/09/2026, thời gian build 48 giờ.
- Hạn đã xác định từ trang sự kiện/email: **27/09/2026 lúc 23:00 Singapore**, tương đương **22:00 Việt Nam**.
- Không chờ đến giờ cuối để tạo `bob_sessions`, quay video hoặc upload MP4.

## Thông tin cần người dùng báo lại cho Claude

Sau khi hoàn tất preflight, gửi đúng năm dòng sau, không gửi mật khẩu/token:

```text
IBMid đúng email đăng ký: OK / CHƯA
Email invite IBM Bob: ĐÃ NHẬN / CHƯA NHẬN
Bob IDE version: ...
Instance đang chọn: ... / region: ...
Bobcoins hiển thị: ...
```

Claude chỉ bắt đầu kế hoạch tiêu Bobcoins cho các experiment sau khi năm mục này hợp lệ.
