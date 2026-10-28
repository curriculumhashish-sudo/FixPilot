import { Agent, ConversationManager, HttpError, Workspace } from '../../index';
import { ConversationClient } from '../../clients';
import { getServerTestConfig } from './test-config';
import {
  deleteWorkspaceFile,
  readWorkspaceFile,
  removeWorkspacePath,
  sleep,
  uniqueDirName,
  uniqueFileName,
  workspaceFileExists,
  writeWorkspaceFile,
} from './test-utils';

const config = getServerTestConfig();

function createDummyAgent(): Agent {
  return new Agent({
    llm: {
      model: 'dummy/model',
      api_key: 'dummy-key',
    },
  });
}

describe('Deterministic API Integration Tests', () => {
  const manager = new ConversationManager({
    host: config.agentServerUrl,
  });
  const workspace = new Workspace({
    host: config.agentServerUrl,
    workingDir: config.agentWorkspaceDir,
  });

  afterAll(() => {
    manager.close();
    workspace.close();
  });

  it(
    'reads server, metadata, settings, tools, and skills endpoints',
    async () => {
      const root = await manager.server.getRoot<Record<string, unknown>>();
      const alive = await manager.server.getAlive();
      const health = await manager.server.getHealth();
      const ready = await manager.server.getReady();
      const info = await manager.server.getServerInfo();

      const providers = await manager.llm.getProviders();
      const models = await manager.llm.getModels();
      const verifiedModels = await manager.llm.getVerifiedModels();
      const agentSchema = await manager.settings.getAgentSchema();
      const conversationSchema = await manager.settings.getConversationSchema();
      const tools = await manager.tools.listTools();
      const skills = await manager.skills.getSkills({
        load_public: false,
        load_user: false,
        load_project: false,
        load_org: false,
      });
      const subAgents = await manager.subAgents.getSubAgents({
        load_user: false,
        load_project: false,
        load_builtin: true,
      });
      const vscodeStatus = await manager.vscode.getStatus();

      expect(root).toBeDefined();
      expect(alive.status).toBe('ok');
      expect(health.status).toBe('ok');
      expect(['ready', 'initializing']).toContain(ready.status);
      expect(info.version).toBeDefined();
      expect(Array.isArray(providers)).toBe(true);
      expect(Array.isArray(models)).toBe(true);
      expect(typeof verifiedModels).toBe('object');
      expect(agentSchema.model_name).toBeTruthy();
      expect(conversationSchema.model_name).toBeTruthy();
      expect(Array.isArray(tools)).toBe(true);
      expect(Array.isArray(skills.skills)).toBe(true);
      // `load_builtin` 发现是尽力而为的并且可以为空 (e.g. 冻结的智能体服务器映像没有内置智能体文件），因此断言合约形状而不是特定计数。 任何从内置请求返回的智能体都必须被标记 `is_builtin`。 下面的专门测试端到端地练习了项目级发现。
      //
      expect(Array.isArray(subAgents.agents)).toBe(true);
      expect(subAgents.agents.every((agent) => agent.is_builtin)).toBe(true);
      expect(typeof vscodeStatus.enabled).toBe('boolean');
    },
    config.testTimeout
  );

  it(
    'discovers a project-level sub-agent from the workspace',
    async () => {
      // 将基于文件的智能体放入工作区中，并确认只读 POST /api/sub-agents 端点无损地发现它。
      //
      const agentName = uniqueDirName('it-sub-agent');
      const agentPath = `.openhands/agents/${agentName}.md`;
      writeWorkspaceFile(
        agentPath,
        [
          '---',
          `name: ${agentName}`,
          'description: Integration-test project sub-agent.',
          'model: inherit',
          'tools:',
          '  - bash',
          '---',
          'You are an integration-test project sub-agent.',
        ].join('\n')
      );

      try {
        const response = await manager.subAgents.getSubAgents({
          load_user: false,
          load_project: true,
          load_builtin: false,
          project_dir: config.agentWorkspaceDir,
        });

        expect(Array.isArray(response.agents)).toBe(true);
        const discovered = response.agents.find((agent) => agent.name === agentName);
        expect(discovered).toBeDefined();
        expect(discovered?.level).toBe('project');
        expect(discovered?.is_builtin).toBe(false);
        expect(discovered?.description).toBe('Integration-test project sub-agent.');
        expect(discovered?.tools).toEqual(['bash']);
        expect(discovered?.system_prompt).toContain('integration-test project sub-agent');
        expect(discovered?.source).toContain(agentPath);
      } finally {
        // 删除此测试创建的整个 `.openhands` 树，而不仅仅是智能体文件。 从主机写入它会留下测试运行者用户拥有的目录； 如果留下，智能体-server 容器（以不同用户身份运行）稍后将无法 chmod
        // `workspace/.openhands` 在配置文件激活期间（“不允许操作”-> 500 无法激活配置文件）。
        //
        removeWorkspacePath('.openhands');
      }
    },
    config.testTimeout
  );

  it(
    'supports deterministic conversation, event, fork, and ACP endpoints',
    async () => {
      const beforeCount = await manager.countConversations();
      const conversation = await manager.createConversation(createDummyAgent(), {
        workingDir: config.agentWorkspaceDir,
      });
      let forkedId: string | undefined;
      let acpConversationId: string | undefined;

      try {
        const afterCount = await manager.countConversations();
        expect(afterCount).toBeGreaterThanOrEqual(beforeCount);

        const batch = await manager.getConversations([conversation.id]);
        expect(batch[0]?.id).toBe(conversation.id);

        await conversation.sendMessage('Deterministic integration message');
        const searchResult = await conversation.state.events.search({
          limit: 10,
          sort_order: 'TIMESTAMP_DESC',
        });
        expect(searchResult.items.length).toBeGreaterThan(0);

        const eventId = searchResult.items[0].id;
        const fetchedEvent = await conversation.state.events.getEventById(eventId);
        const fetchedBatch = await conversation.state.events.getEventsById([eventId]);
        expect(fetchedEvent.id).toBe(eventId);
        expect(fetchedBatch[0]?.id).toBe(eventId);

        const finalResponse = await conversation.getAgentFinalResponse();
        expect(typeof finalResponse).toBe('string');

        const trajectory = await conversation.downloadTrajectory();
        expect(trajectory).toBeInstanceOf(Blob);
        expect(trajectory.size).toBeGreaterThan(0);
        const trajectoryBytes = new Uint8Array(await trajectory.arrayBuffer());
        // 验证它是有效的 ZIP 文件（PK\x03\x04 魔法字节）
        expect(trajectoryBytes[0]).toBe(0x50); // P
        expect(trajectoryBytes[1]).toBe(0x4b); // K

        const forkedConversation = await conversation.fork({
          title: 'Forked from deterministic test',
        });
        forkedId = forkedConversation.id;
        expect(forkedConversation.id).not.toBe(conversation.id);

        await expect(
          conversation.switchProfile('__profile_that_should_not_exist__')
        ).rejects.toBeInstanceOf(HttpError);

        // switchLlm 交换 LLM 按位，键值 usage_id （以先写者胜） 注册表). 重用智能体'现有的' usage_id 将会是一个无声无息的操作，所以请使用一个新的，然后读回模型智能体证明交换确实生效。
        //
        await conversation.switchLlm({
          model: 'dummy/switched-model',
          api_key: 'dummy-key',
          usage_id: 'switched',
        });
        const switchedAgent = await conversation.state.getAgent();
        expect(switchedAgent.llm.model).toBe('dummy/switched-model');

        const acpConversation = await manager.acp.createConversation(
          {
            kind: 'Agent',
            llm: { model: 'dummy/model', api_key: 'dummy-key' },
          },
          { workingDir: config.agentWorkspaceDir }
        );
        acpConversationId = acpConversation.id;

        const acpCount = await manager.acp.countConversations();
        const fetchedACP = await manager.acp.getConversation(acpConversation.id);
        const batchACP = await manager.acp.getConversations([acpConversation.id]);
        expect(acpCount).toBeGreaterThan(0);
        expect(fetchedACP.id).toBe(acpConversation.id);
        expect(batchACP[0]?.id).toBe(acpConversation.id);
      } finally {
        if (forkedId) {
          await manager.deleteConversation(forkedId).catch(() => undefined);
        }
        if (acpConversationId) {
          await manager.deleteConversation(acpConversationId).catch(() => undefined);
        }
        await manager.deleteConversation(conversation.id).catch(() => undefined);
      }
    },
    config.testTimeout
  );

  it(
    'uses preferred workspace file and git query endpoints',
    async () => {
      const fileName = uniqueFileName('deterministic-workspace');
      const fileContent = 'workspace content from deterministic test';
      const destinationPath = `${config.agentWorkspaceDir}/${fileName}`;
      const repoDir = `${config.agentWorkspaceDir}/git-query-test`;
      const trackedFile = `${repoDir}/tracked.txt`;

      try {
        const uploadResult = await workspace.uploadText(fileContent, destinationPath, fileName);
        expect(uploadResult.success).toBe(true);

        await sleep(300);
        expect(workspaceFileExists(fileName)).toBe(true);
        expect(readWorkspaceFile(fileName)).toBe(fileContent);

        const downloaded = await workspace.downloadAsText(destinationPath);
        expect(downloaded).toBe(fileContent);

        await workspace.executeCommand(
          [
            `rm -rf ${repoDir}`,
            `mkdir -p ${repoDir}`,
            `cd ${repoDir}`,
            'git init',
            'git config user.email tester@example.com',
            'git config user.name tester',
            'printf "line1\\n" > tracked.txt',
            'git add tracked.txt',
            'git commit -m initial',
            'printf "line2\\n" >> tracked.txt',
          ].join(' && ')
        );

        const changes = await workspace.gitChanges(repoDir);
        const diff = await workspace.gitDiff(trackedFile);

        expect(changes.some((change) => String(change.path).includes('tracked.txt'))).toBe(true);
        expect(diff.modified || diff.diff).toContain('line2');

        const headChanges = await workspace.gitChanges(repoDir, { ref: 'HEAD' });
        expect(headChanges.some((change) => String(change.path).includes('tracked.txt'))).toBe(
          true
        );

        const headDiff = await workspace.gitDiff(trackedFile, { ref: 'HEAD' });
        expect(headDiff.modified || headDiff.diff).toContain('line2');
      } finally {
        deleteWorkspaceFile(fileName);
        await workspace.executeCommand(`rm -rf ${repoDir}`);
      }
    },
    config.testTimeout
  );

  it(
    'round-trips a profile through save, get, list, activate, rename, and delete',
    async () => {
      const profileName = uniqueDirName('it-profile');
      const renamedProfile = `${profileName}-renamed`;
      const llm = { model: 'dummy/model', api_key: 'dummy-key' };

      try {
        const saved = await manager.profiles.saveProfile(profileName, { llm });
        expect(saved.name).toBe(profileName);

        const detail = await manager.profiles.getProfile(profileName);
        expect(detail.name).toBe(profileName);
        // 已保存的 LLM 配置往返...
        expect(detail.config.model).toBe('dummy/model');
        // ...but the default (no X-Expose-Secrets) response nulls api_key and
        // 相反，通过 api_key_set 报告已保存密钥的存在。
        expect(detail.config.api_key).toBeNull();
        expect(detail.api_key_set).toBe(true);

        const list = await manager.profiles.listProfiles();
        expect(list.profiles.some((profile) => profile.name === profileName)).toBe(true);

        const activated = await manager.profiles.activateProfile(profileName);
        expect(activated.name).toBe(profileName);
        expect(activated.llm_applied).toBe(true);

        const afterActivate = await manager.profiles.listProfiles();
        expect(afterActivate.active_profile).toBe(profileName);

        const renamed = await manager.profiles.renameProfile(profileName, renamedProfile);
        expect(renamed.name).toBe(renamedProfile);

        const renamedDetail = await manager.profiles.getProfile(renamedProfile);
        expect(renamedDetail.name).toBe(renamedProfile);
        // 配置在（原子）重命名后仍然存在......
        expect(renamedDetail.config.model).toBe('dummy/model');
        // ...and because the renamed profile was the active one, the
        // active_profile 指针跟随它指向新名称。
        const afterRename = await manager.profiles.listProfiles();
        expect(afterRename.active_profile).toBe(renamedProfile);
        // 配置文件重命名后，原始名称将停止解析。
        await expect(manager.profiles.getProfile(profileName)).rejects.toBeInstanceOf(HttpError);

        const deleted = await manager.profiles.deleteProfile(renamedProfile);
        expect(deleted.name).toBe(renamedProfile);

        const finalList = await manager.profiles.listProfiles();
        expect(finalList.profiles.some((profile) => profile.name === renamedProfile)).toBe(false);
      } finally {
        await manager.profiles.deleteProfile(profileName).catch(() => undefined);
        await manager.profiles.deleteProfile(renamedProfile).catch(() => undefined);
      }
    },
    config.testTimeout
  );

  it(
    'switchAcpModel reaches the route and rejects a non-ACP conversation with 400',
    async () => {
      // switchAcpModel 的合约防护针对真实的智能体服务器。 软件-智能体-SDK#3390中添加了路线POST/api/conversations/{id}/switch_acp_model； 非 ACP 对话在没有 ACP 凭据或真实模型切换的情况下练习它。 一个400（不是404）证明了客户端指向的 pinned 图像 AND 上的路径和体存在，从而捕获了客户端<->服务器合同的漂移模拟的单元测试。
      //
      const conversation = await manager.createConversation(createDummyAgent(), {
        workingDir: config.agentWorkspaceDir,
      });
      try {
        let status: number | undefined;
        try {
          await conversation.switchAcpModel('claude-haiku-4-5');
        } catch (error) {
          expect(error).toBeInstanceOf(HttpError);
          status = (error as HttpError).status;
        }
        expect(status).toBe(400);
      } finally {
        await manager.deleteConversation(conversation.id).catch(() => undefined);
      }
    },
    config.testTimeout
  );

  it(
    'exercises the /goal, /goal/resume, and /goal/stop routes without an LLM',
    async () => {
      // 球门的合同守卫端点（软件-智能体-SDK #3770，在 v1.29.0 中发布 - 固定图像）。 这些故意远离快乐路径，因此它们既不需要真正的 LLM 也不需要后台循环：
      //   - 从空目标开始被 GoalController -> 400 拒绝
      //   - 恢复，没有任何内容可以继续 -> 400 ("no_resumable_goal")
      //   - 没有活动循环的停止是无操作成功 -> 200
      // 400/200（不是404）证明了每个路由存在于图像中 AND 客户端应该选择正确的路径/方法/体<->服务器合同漂移模拟的单元测试无法捕捉。
      //
      const conversation = await manager.createConversation(createDummyAgent(), {
        workingDir: config.agentWorkspaceDir,
      });
      try {
        let startStatus: number | undefined;
        try {
          await conversation.startGoal('');
        } catch (error) {
          expect(error).toBeInstanceOf(HttpError);
          startStatus = (error as HttpError).status;
        }
        expect(startStatus).toBe(400);

        let resumeStatus: number | undefined;
        try {
          await conversation.resumeGoal();
        } catch (error) {
          expect(error).toBeInstanceOf(HttpError);
          resumeStatus = (error as HttpError).status;
        }
        expect(resumeStatus).toBe(400);

        // 当没有目标循环运行时停止是无操作成功，而不是错误。
        await expect(conversation.stopGoal()).resolves.toBeUndefined();
      } finally {
        await manager.deleteConversation(conversation.id).catch(() => undefined);
      }
    },
    config.testTimeout
  );

  it(
    'returns 404 from the goal endpoints for an unknown conversation',
    async () => {
      // 格式良好但不存在的对话 UUID 解析为路径参数并到达每个处理程序，该处理程序必须回答 404。 这是有区别的
      //
      // from a 422 (malformed UUID) or 405 (wrong method on a missing route),
      // 因此它确认了路由模板解析，并且未找到的分支已连接到所有三个目标端点。
      //
      const client = new ConversationClient({ host: config.agentServerUrl });
      const missingId = '00000000-0000-0000-0000-000000000000';
      try {
        const calls: Array<() => Promise<unknown>> = [
          () => client.startGoal(missingId, { objective: 'noop' }),
          () => client.resumeGoal(missingId),
          () => client.stopGoal(missingId),
        ];
        for (const call of calls) {
          let status: number | undefined;
          try {
            await call();
          } catch (error) {
            expect(error).toBeInstanceOf(HttpError);
            status = (error as HttpError).status;
          }
          expect(status).toBe(404);
        }
      } finally {
        client.close();
      }
    },
    config.testTimeout
  );

  it(
    'reaches the skills refresh route and 404s for an uninstalled skill',
    async () => {
      // POST /api/skills/installed/{name}/refresh 的合同守卫 (路由是 /refresh，而不是 /update). 一个有效的但未安装的技能名称到达处理器，处理器必须返回 404 —— 证明路由存在于图像中，客户端则会指向正确的路径。)
      //
      let status: number | undefined;
      try {
        await manager.skills.refreshSkill('nonexistent-skill');
      } catch (error) {
        expect(error).toBeInstanceOf(HttpError);
        status = (error as HttpError).status;
      }
      expect(status).toBe(404);
    },
    config.testTimeout
  );

  it(
    'navigate re-roots the HEAD across existing events and back to the empty tree',
    async () => {
      // 合同 + 语义保护 POST  /api/conversations/{id}/navigate (软件-智能体-SDK #3923，发布于 v1.31.0 — 固定的镜像）。 两个用户消息创建了 >=2 个事件 LLM; 导航后，对话会移动 HEAD (leaf_event_id在他们之间 —— 没有分支，没有新的对话。 这证明了该路线存在于图像中 AND 客户端应该选择正确的路径/身体，而不是返回新叶<->服务器合同漂移模拟的单元测试无法捕捉。
      //
      const client = new ConversationClient({ host: config.agentServerUrl });
      const conversation = await manager.createConversation(createDummyAgent(), {
        workingDir: config.agentWorkspaceDir,
      });
      try {
        await conversation.sendMessage('First navigate message');
        await conversation.sendMessage('Second navigate message');

        // 升序排序 => items[0] 是最早的事件，最后一个是尾部事件。
        const events = await conversation.state.events.search({
          limit: 50,
          sort_order: 'TIMESTAMP',
        });
        expect(events.items.length).toBeGreaterThanOrEqual(2);
        const firstEventId = events.items[0].id;
        const lastEventId = events.items[events.items.length - 1].id;

        // 将 HEAD 重新定位到最早的事件； 回应带来新的一页。
        const rerooted = await client.navigateConversation(conversation.id, {
          event_id: firstEventId,
        });
        expect(rerooted.leaf_event_id).toBe(firstEventId);

        // A null event_id 选择空树（故意的新根）。
        const emptied = await client.navigateConversation(conversation.id, {
          event_id: null,
        });
        expect(emptied.leaf_event_id).toBeNull();

        // 高层包装器到达相同的路由并刷新缓存状态而不抛出； 将 HEAD 恢复到原始尾部，并将其从服务器读回以证明移动已持久化。
        //
        await conversation.navigateTo(lastEventId);
        const restored = await manager.getConversations([conversation.id]);
        expect(restored[0]?.leaf_event_id).toBe(lastEventId);
      } finally {
        client.close();
        await manager.deleteConversation(conversation.id).catch(() => undefined);
      }
    },
    config.testTimeout
  );

  it(
    'navigate 404s for an unknown conversation and an unknown event id',
    async () => {
      // 导航路线的两个未找到分支。 格式良好但不存在的对话 UUID 到达处理程序 ->“未找到对话”404。 与虚假 event_id 的真实对话会到达服务器的 event_id ValueError 分支 -> 404（不是 500）。 它们一起确认路由模板已解析，并且两条未找到的路径均已连接。
      //
      const client = new ConversationClient({ host: config.agentServerUrl });
      const missingId = '00000000-0000-0000-0000-000000000000';
      const conversation = await manager.createConversation(createDummyAgent(), {
        workingDir: config.agentWorkspaceDir,
      });
      try {
        let unknownConversationStatus: number | undefined;
        try {
          await client.navigateConversation(missingId, { event_id: null });
        } catch (error) {
          expect(error).toBeInstanceOf(HttpError);
          unknownConversationStatus = (error as HttpError).status;
        }
        expect(unknownConversationStatus).toBe(404);

        let unknownEventStatus: number | undefined;
        try {
          await client.navigateConversation(conversation.id, {
            event_id: 'event-that-does-not-exist',
          });
        } catch (error) {
          expect(error).toBeInstanceOf(HttpError);
          unknownEventStatus = (error as HttpError).status;
        }
        expect(unknownEventStatus).toBe(404);
      } finally {
        client.close();
        await manager.deleteConversation(conversation.id).catch(() => undefined);
      }
    },
    config.testTimeout
  );
});
